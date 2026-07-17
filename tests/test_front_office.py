"""Front-office coverage — the sonarzum rule, enforced forever.

Origin: the workspace-agent site builder (which built and published the
"sonarzum" site) rusted invisible for months because only port-services were
registered in services.json. These tests make that failure mode impossible to
reintroduce silently:

  * every top-level organ dir must be accounted for (service / capability /
    conscious ignore) — the suite goes red the day someone builds an organ
    without giving it a front-door presence;
  * every capability card must be honest: required fields present, its home
    dir real, and its slash-command entry point actually installed.
"""

import importlib.util
import json
import os
import re
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import audit_services  # noqa: E402

REGISTRY = os.path.join(ROOT, "services.json")
_REQUIRED = ("key", "name", "desc", "icon", "cat", "home", "kind", "invoke")
_KINDS = {"slash", "cli", "agent", "extension"}


def _registry() -> dict:
    with open(REGISTRY, encoding="utf-8") as f:
        return json.load(f)


class CapabilityCards(unittest.TestCase):
    def setUp(self):
        self.reg = _registry()
        self.caps = self.reg.get("capabilities", [])

    def test_registry_has_capability_section(self):
        self.assertGreater(len(self.caps), 0, "capabilities section missing/empty")

    def test_required_fields_and_kinds(self):
        for c in self.caps:
            for field in _REQUIRED:
                self.assertTrue(str(c.get(field, "")).strip(),
                                f"{c.get('key', '?')}: '{field}' boşdur")
            self.assertIn(c["kind"], _KINDS, f"{c['key']}: naməlum kind {c['kind']}")

    def test_keys_unique_across_services_and_capabilities(self):
        keys = ([s["key"] for s in self.reg["services"]]
                + [c["key"] for c in self.caps])
        self.assertEqual(len(keys), len(set(keys)), "təkrarlanan key var")

    def test_capability_homes_exist(self):
        for c in self.caps:
            self.assertTrue(os.path.isdir(os.path.join(ROOT, c["home"])),
                            f"{c['key']}: home yoxdur → {c['home']}")

    def test_slash_invokes_are_real_commands(self):
        """A '/xyz' promised on a card must exist as an installed command —
        the steward never fabricates an entry point."""
        cmd_dir = os.path.join(ROOT, "claude-agents", ".claude", "commands")
        for c in self.caps:
            if c["kind"] != "slash":
                continue
            slashes = [w for w in c["invoke"].replace("·", " ").split()
                       if w.startswith("/") and len(w) > 1]
            self.assertTrue(slashes, f"{c['key']}: slash invoke-da /əmr yoxdur")
            for s in slashes:
                name = s.lstrip("/").strip(".,;:")
                self.assertTrue(
                    os.path.isfile(os.path.join(cmd_dir, f"{name}.md")),
                    f"{c['key']}: /{name} əmri quraşdırılmayıb ({cmd_dir})")


class OrganCoverage(unittest.TestCase):
    """The standing guard: the real repo must always be fully accounted for."""

    def test_every_organ_is_on_the_shelf(self):
        org = audit_services.organ_coverage(_registry())
        self.assertEqual(org["unaccounted"], [],
                         "Vitrinsiz orqan(lar): services.json-da yer ver — "
                         f"{org['unaccounted']}")
        self.assertEqual(org["missing_home"], [],
                         f"Qabiliyyət evi itib: {org['missing_home']}")

    def test_new_unregistered_organ_is_flagged(self):
        """Negative proof: an organ dir with no registry presence turns red."""
        with tempfile.TemporaryDirectory(prefix="fo_") as tmp:
            os.mkdir(os.path.join(tmp, "mystery-studio"))
            os.mkdir(os.path.join(tmp, "docs"))  # support dir — must NOT flag
            saved = audit_services.ROOT
            audit_services.ROOT = tmp
            try:
                org = audit_services.organ_coverage(
                    {"services": [], "capabilities": [], "audit_ignore_dirs": []})
            finally:
                audit_services.ROOT = saved
        self.assertEqual(org["unaccounted"], ["mystery-studio"])

    def test_dir_dot_service_home_resolved_from_target(self):
        """dir='.' services (media_studio, seo, …) must still account for their
        module dir via the uvicorn target."""
        dirs = audit_services._service_dirs(_registry()["services"])
        self.assertIn("media_studio", dirs)
        self.assertIn("seo", dirs)
        self.assertIn("gateway", dirs)


class AdvisorFrontDoor(unittest.TestCase):
    def test_front_door_findings_never_raise(self):
        from gateway import advisor
        out = advisor._front_door_findings()
        self.assertIsInstance(out, list)
        # repo is fully accounted right now → no front_door_gap finding
        self.assertNotIn("front_door_gap", {f.code for f in out})

    def test_synthetic_snapshot_skips_repo_audit(self):
        """observe_state(snap) must stay pure over the snapshot — tests and
        replays make no claim about the repo's front door."""
        os.environ["ADVISOR_DISABLE_LLM"] = "1"
        try:
            from gateway import advisor
            f = advisor.observe_state({
                "env": {"RAPIDAPI_KEY": "SET (len=36, …EF99)"},
                "queue": {}, "memory": {}, "llm": {}, "git": {"head": "abc", "dirty": False},
                "contradictions": [],
            })
            self.assertFalse({"front_door_gap", "port_drift", "registry_ghost"}
                             & {x.code for x in f})
        finally:
            os.environ.pop("ADVISOR_DISABLE_LLM", None)


class AnatomyMap(unittest.TestCase):
    """Canlı Anatomiya — the hub's live flow map. The organs band renders from
    the registry at runtime; here we pin the map's spine: pane + nav exist and
    every flow wire connects two nodes that are actually defined."""

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(ROOT, "hub", "templates", "portal.html"),
                  encoding="utf-8") as f:
            cls.html = f.read()

    def test_anatomy_pane_and_nav_exist(self):
        self.assertIn('id="anatomy"', self.html)
        self.assertIn("Canlı Anatomiya", self.html)
        self.assertIn("showAnatomy", self.html)
        self.assertIn("paintAnatomyDots", self.html)

    def test_flow_edges_reference_defined_nodes(self):
        node_ids = set(re.findall(r"\{id:'(\w+)'", self.html))
        edges = re.findall(r"\['(\w+)','(\w+)'(?:,'[^']*')?\]", self.html)
        self.assertGreaterEqual(len(node_ids), 15, "flow xəritəsi kiçilib?")
        self.assertGreaterEqual(len(edges), 15)
        for a, b in edges:
            self.assertIn(a, node_ids, f"tel açıq qalıb: {a}")
            self.assertIn(b, node_ids, f"tel açıq qalıb: {b}")

    def test_key_organs_of_the_spine_present(self):
        for organ in ("Bir Mikrofon", "Növbə", "İcraçı", "Model Qapısı",
                      "Sənin təsdiqin", "Brain yaddaşı"):
            self.assertIn(organ, self.html, f"onurğa orqanı itib: {organ}")


class HubApi(unittest.TestCase):
    def test_hub_serves_capability_cards(self):
        try:
            spec = importlib.util.spec_from_file_location(
                "hub_app", os.path.join(ROOT, "hub", "app.py"))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        except ImportError as exc:  # hub venv deps not present here
            self.skipTest(f"hub deps unavailable: {exc}")
        body = json.loads(mod.capabilities().body)
        self.assertEqual(len(body), len(_registry().get("capabilities", [])))
        self.assertIn("site-studio", {c["key"] for c in body})


if __name__ == "__main__":
    unittest.main()
