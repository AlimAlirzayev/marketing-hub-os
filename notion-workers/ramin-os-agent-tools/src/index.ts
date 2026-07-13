import { Worker } from "@notionhq/workers";
import { j } from "@notionhq/workers/schema-builder";

const worker = new Worker();
export default worker;

const WORK_TYPE_ROUTES = {
	campaign: {
		owner: "Publisher + Atelier",
		entryPoint: "publisher / atelier",
		nextStep: "Create a draft campaign package, then run Publisher dry-run before any public action.",
	},
	content: {
		owner: "Copy Studio + Creative Studio",
		entryPoint: "copy-studio / atelier",
		nextStep: "Prepare copy and creative drafts, then pass exact legal copy through local QA.",
	},
	analytics: {
		owner: "Ads Studio + GA4 Studio",
		entryPoint: "ads-studio / ga4-studio",
		nextStep: "Use analytics modules for reporting; do not paste raw customer records into Notion AI.",
	},
	cx: {
		owner: "CX Command Center",
		entryPoint: "cx-command-center",
		nextStep: "Use redacted complaint summaries only; customer-facing replies require human approval.",
	},
	research: {
		owner: "Influencer Hunter + Price Hunter + SEO Studio",
		entryPoint: "influencer-hunter / price-hunter / seo",
		nextStep: "Route research to the owning radar module and keep evidence links with the draft.",
	},
	system: {
		owner: "Gateway Panel",
		entryPoint: "gateway.panel",
		nextStep: "Queue safe work through the gateway; risky actions must stop at the approval rail.",
	},
	other: {
		owner: "Gateway Queue",
		entryPoint: "gateway.queue",
		nextStep: "Convert the request into a scoped gateway task with clear inputs and expected output.",
	},
} as const;

const BLOCKED_INPUT_PATTERNS = [
	{
		key: "secrets",
		terms: ["api key", "apikey", "token", "password", "secret", "cookie", ".env", "credential"],
		reason: "Secrets, tokens, cookies, credentials, and .env content must not be sent to this worker.",
	},
	{
		key: "customer_data",
		terms: ["customer", "client", "claim", "policy number", "phone", "passport", "fin code", "complaint"],
		reason: "Raw customer data, claims, policies, and complaint evidence must stay in approved local systems.",
	},
	{
		key: "payment_data",
		terms: ["card", "payment", "invoice", "billing", "checkout", "bank account", "iban"],
		reason: "Payment and billing material is blocked for autonomous Notion agent tools.",
	},
	{
		key: "private_strategy",
		terms: ["private strategy", "internal strategy", "board", "confidential", "unredacted"],
		reason: "Private strategy must be redacted before it leaves the local Ramin-OS boundary.",
	},
] as const;

const RISKY_ACTION_TERMS = [
	"publish",
	"post",
	"send",
	"email",
	"sms",
	"call",
	"deploy",
	"delete",
	"archive",
	"pay",
	"purchase",
	"book",
	"subscribe",
	"gonder",
	"paylas",
	"yayinla",
	"sil",
	"zeng",
] as const;

type WorkType = keyof typeof WORK_TYPE_ROUTES;

function normalizeText(...parts: Array<string | null | undefined>): string {
	return parts
		.filter((part): part is string => Boolean(part))
		.join(" ")
		.toLowerCase();
}

function detectBlockedInputs(text: string, explicitFlags: string[] = []) {
	const matched = BLOCKED_INPUT_PATTERNS.filter((pattern) =>
		explicitFlags.includes(pattern.key) || pattern.terms.some((term) => text.includes(term)),
	);

	return {
		keys: matched.map((item) => item.key),
		reasons: matched.map((item) => item.reason),
	};
}

function detectRiskyAction(text: string): string[] {
	return RISKY_ACTION_TERMS.filter((term) => text.includes(term));
}

function buildApprovalReasons(input: {
	publicFacing?: boolean;
	sendsMessage?: boolean;
	changesProduction?: boolean;
	deletesOrArchives?: boolean;
	spendsMoney?: boolean;
	needsExternalAction?: boolean;
	needsPublishing?: boolean;
	riskyTerms?: string[];
}) {
	const reasons: string[] = [];
	if (input.publicFacing || input.needsPublishing) reasons.push("Public-facing publish/post action.");
	if (input.sendsMessage) reasons.push("Outbound message or reply.");
	if (input.changesProduction || input.needsExternalAction) reasons.push("Production or external system change.");
	if (input.deletesOrArchives) reasons.push("Delete/archive action.");
	if (input.spendsMoney) reasons.push("Payment, booking, subscription, or spend action.");
	if (input.riskyTerms?.length) reasons.push(`Risk terms detected: ${input.riskyTerms.join(", ")}.`);
	return reasons;
}

worker.tool("screenRaminOsAction", {
	title: "Screen Ramin-OS Action",
	description:
		"Check whether a proposed Ramin-OS action is safe as a draft, requires human approval, or is blocked.",
	hints: { readOnlyHint: true },
	schema: j.object({
		action: j.string().describe("The action the Notion agent or user wants Ramin-OS to perform."),
		target: j.string().nullable().describe("The target system, channel, page, campaign, or customer record, or null."),
		publicFacing: j.boolean().describe("True when the action would be visible to customers or the public."),
		sendsMessage: j.boolean().describe("True when the action sends, replies, calls, posts, or notifies anyone."),
		changesProduction: j.boolean().describe("True when the action writes to production systems or external accounts."),
		deletesOrArchives: j.boolean().describe("True when the action deletes, archives, wipes, or disables anything."),
		spendsMoney: j.boolean().describe("True when the action buys, pays, books, subscribes, or spends credits."),
		containsSecrets: j.boolean().describe("True when the prompt includes keys, tokens, cookies, or credentials."),
		containsCustomerData: j.boolean().describe("True when raw customer, claim, policy, complaint, or payment data appears."),
		containsClaimsOrPolicies: j.boolean().describe("True when insurance claim or policy details appear."),
	}),
	execute: (input) => {
		const text = normalizeText(input.action, input.target);
		const explicitBlocked = [
			input.containsSecrets ? "secrets" : "",
			input.containsCustomerData || input.containsClaimsOrPolicies ? "customer_data" : "",
			input.spendsMoney ? "payment_data" : "",
		].filter(Boolean);
		const blockedInputs = detectBlockedInputs(text, explicitBlocked);
		const riskyTerms = detectRiskyAction(text);
		const approvalReasons = buildApprovalReasons({ ...input, riskyTerms });

		const gate =
			blockedInputs.keys.length > 0
				? "blocked"
				: approvalReasons.length > 0
					? "approval_required"
					: "safe_draft";

		return {
			gate,
			allowedAutonomously: gate === "safe_draft",
			requiresHumanApproval: gate === "approval_required",
			blockedInputs: blockedInputs.keys,
			reasons: [...blockedInputs.reasons, ...approvalReasons],
			route: gate === "safe_draft" ? "Draft inside Notion or hand off to the Ramin-OS gateway." : "Ramin-OS approval rail.",
			nextStep:
				gate === "blocked"
					? "Redact or remove blocked material before continuing."
					: gate === "approval_required"
						? "Prepare an approval checkpoint with the exact action, target, and risk."
						: "Proceed only as a draft/read-only action.",
			controls: [
				"Do not read, paste, print, or upload secrets.",
				"Do not send customer data, claims, policies, payment data, or private strategy to this worker.",
				"Do not publish, send, spend, delete, deploy, or write production data without human approval.",
			],
		};
	},
});

worker.tool("prepareRaminOsHandoff", {
	title: "Prepare Ramin-OS Handoff",
	description:
		"Turn a Notion brief into a structured, redaction-aware handoff for the right Ramin-OS module.",
	hints: { readOnlyHint: true },
	schema: j.object({
		workType: j
			.enum("campaign", "content", "analytics", "cx", "research", "system", "other")
			.describe("The closest Ramin-OS work category."),
		brief: j.string().describe("The redacted brief or request. Do not include secrets or raw customer records."),
		desiredOutput: j.string().nullable().describe("The expected deliverable, or null when undecided."),
		sourceLocation: j.string().nullable().describe("Optional Notion page title or non-secret source label."),
		deadline: j.string().nullable().describe("Optional deadline as plain text or ISO date, or null."),
		hasSensitiveInputs: j.boolean().describe("True if the brief still contains sensitive or unredacted inputs."),
		needsExternalAction: j.boolean().describe("True if the final work would call, write, deploy, or affect another system."),
		needsPublishing: j.boolean().describe("True if the final work would be published or sent externally."),
	}),
	execute: (input) => {
		const route = WORK_TYPE_ROUTES[input.workType as WorkType] ?? WORK_TYPE_ROUTES.other;
		const text = normalizeText(input.brief, input.desiredOutput, input.sourceLocation);
		const blockedInputs = detectBlockedInputs(text, input.hasSensitiveInputs ? ["private_strategy"] : []);
		const riskyTerms = detectRiskyAction(text);
		const approvalReasons = buildApprovalReasons({
			needsExternalAction: input.needsExternalAction,
			needsPublishing: input.needsPublishing,
			riskyTerms,
		});

		const gate =
			blockedInputs.keys.length > 0
				? "blocked_until_redacted"
				: approvalReasons.length > 0
					? "draft_then_approval"
					: "draft_ready";

		return {
			gate,
			moduleOwner: route.owner,
			entryPoint: route.entryPoint,
			sourceLocation: input.sourceLocation,
			deadline: input.deadline,
			desiredOutput: input.desiredOutput,
			blockedInputs: blockedInputs.keys,
			riskReasons: [...blockedInputs.reasons, ...approvalReasons],
			handoff: {
				title: `${input.workType}: ${input.desiredOutput ?? "Ramin-OS task"}`,
				brief: input.brief,
				nextAction: gate === "blocked_until_redacted" ? "Redact the brief before queuing." : route.nextStep,
				checklist: [
					"Confirm the brief contains no secrets or raw customer data.",
					"Route to the named Ramin-OS module instead of creating a parallel workflow.",
					"Keep generated work as draft until local QA passes.",
					"Use the gateway approval rail before any publish/send/spend/delete/production write.",
				],
			},
		};
	},
});
