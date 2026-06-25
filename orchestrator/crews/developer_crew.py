"""Xalq Insurance Digital OS - Developer crew.

Six agents covering the software development domain. In practice the developer
domain is driven mainly by Claude Code subagents; this crew is the CrewAI-side
mirror for tasks orchestrated from Python. Skeleton with LLM wiring left as TODO.
"""

from __future__ import annotations

from crewai import Agent, Crew, Process, Task

AGENT_TIERS: dict[str, str] = {
    "code_writer": "complex",        # Claude - code generation
    "code_reviewer": "complex",      # Claude - careful review
    "security_auditor": "complex",   # Claude - security analysis
    "bug_hunter": "private",         # Ollama - local, no code leaves machine
    "documentation": "free_bulk",    # Gemini - bulk doc generation
    "deployer": "fast",              # Groq - quick deploy decisions
}


def build_agents() -> dict[str, Agent]:
    """Construct the six developer agents."""
    code_writer = Agent(
        role="Code Writer",
        goal="Implement features and fixes from clear specifications",
        backstory=(
            "A senior engineer who writes clean, idiomatic code and keeps "
            "changes minimal and focused."
        ),
        verbose=True,
        allow_delegation=False,
    )
    code_reviewer = Agent(
        role="Code Reviewer",
        goal="Review changes for correctness, style, and maintainability",
        backstory=(
            "A reviewer who catches subtle bugs and enforces consistency "
            "without nitpicking."
        ),
        verbose=True,
        allow_delegation=False,
    )
    security_auditor = Agent(
        role="Security Auditor",
        goal="Find vulnerabilities and insecure patterns before they ship",
        backstory=(
            "A security specialist who thinks like an attacker and flags "
            "OWASP-class issues in proposed changes."
        ),
        verbose=True,
        allow_delegation=False,
    )
    bug_hunter = Agent(
        role="Bug Hunter",
        goal="Reproduce, isolate, and diagnose reported bugs locally",
        backstory=(
            "A debugger who runs entirely on a local model so private code "
            "never leaves the machine."
        ),
        verbose=True,
        allow_delegation=False,
    )
    documentation = Agent(
        role="Documentation Writer",
        goal="Produce and update READMEs, API docs, and changelogs",
        backstory=(
            "A technical writer who keeps docs accurate and in sync with the "
            "codebase."
        ),
        verbose=True,
        allow_delegation=False,
    )
    deployer = Agent(
        role="Deployer",
        goal="Build, containerize, and ship releases safely",
        backstory=(
            "A release engineer who automates deploys and verifies health "
            "before declaring success."
        ),
        verbose=True,
        allow_delegation=False,
    )
    return {
        "code_writer": code_writer,
        "code_reviewer": code_reviewer,
        "security_auditor": security_auditor,
        "bug_hunter": bug_hunter,
        "documentation": documentation,
        "deployer": deployer,
    }


def build_crew(brief: str) -> Crew:
    """Assemble the developer crew for a given brief.

    TODO: attach LLMs via router.get_llm before running in production.
    """
    agents = build_agents()

    implement_task = Task(
        description=(
            f"Implement the following development task: {brief}. Produce the "
            "code change and a short summary of what was modified."
        ),
        expected_output="A code change plus a summary of modified files.",
        agent=agents["code_writer"],
    )

    return Crew(
        agents=list(agents.values()),
        tasks=[implement_task],
        process=Process.sequential,
        verbose=True,
    )


if __name__ == "__main__":
    crew = build_crew(brief="Add a health-check endpoint to the API")
    print(f"Developer crew ready with {len(crew.agents)} agents.")
    # result = crew.kickoff()  # enable once LLM providers are wired
