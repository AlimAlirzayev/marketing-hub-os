"""Xalq Insurance Digital OS - Business crew.

Five agents covering business automation. Skeleton: agent definitions and one
example task are real; LLM wiring is delegated to ``router.get_llm`` (TODO).
"""

from __future__ import annotations

from crewai import Agent, Crew, Process, Task

AGENT_TIERS: dict[str, str] = {
    "lead_generator": "free_bulk",    # Gemini - bulk prospecting
    "cold_caller": "complex",         # Claude - nuanced voice scripts
    "customer_support": "fast",       # Groq - quick ticket triage
    "crm_manager": "fast",            # Groq - lead classification
    "invoice_finance": "complex",     # Claude - careful financial logic
}


def build_agents() -> dict[str, Agent]:
    """Construct the five business agents."""
    lead_generator = Agent(
        role="Lead Generator",
        goal="Find and qualify prospects matching the ideal customer profile",
        backstory=(
            "A prospecting specialist who builds targeted lead lists from "
            "public sources and scores them for fit."
        ),
        verbose=True,
        allow_delegation=False,
    )
    cold_caller = Agent(
        role="Cold Caller",
        goal="Draft and adapt voice call scripts for outbound sales",
        backstory=(
            "A sales conversation designer who writes natural call scripts and "
            "handles objections gracefully."
        ),
        verbose=True,
        allow_delegation=False,
    )
    customer_support = Agent(
        role="Customer Support Agent",
        goal="Answer customer questions and triage support tickets",
        backstory=(
            "A support specialist who resolves common issues from a RAG "
            "knowledge base and escalates only what truly needs a human."
        ),
        verbose=True,
        allow_delegation=False,
    )
    crm_manager = Agent(
        role="CRM Manager",
        goal="Classify, deduplicate, and enrich CRM records",
        backstory=(
            "A data steward who keeps the CRM clean and automatically tags "
            "leads by stage and segment."
        ),
        verbose=True,
        allow_delegation=False,
    )
    invoice_finance = Agent(
        role="Invoice and Finance Agent",
        goal="Generate invoices, reconcile payments, and prepare reports",
        backstory=(
            "A meticulous finance assistant who handles billing and produces "
            "clear summaries for tax and accounting."
        ),
        verbose=True,
        allow_delegation=False,
    )
    return {
        "lead_generator": lead_generator,
        "cold_caller": cold_caller,
        "customer_support": customer_support,
        "crm_manager": crm_manager,
        "invoice_finance": invoice_finance,
    }


def build_crew(brief: str) -> Crew:
    """Assemble the business crew for a given brief.

    TODO: attach LLMs via router.get_llm before running in production.
    """
    agents = build_agents()

    qualify_task = Task(
        description=(
            f"Given this business objective: {brief}. Build a qualified lead "
            "list and classify each lead by ICP fit (high / medium / low)."
        ),
        expected_output="A lead list with ICP-fit classification per lead.",
        agent=agents["lead_generator"],
    )

    return Crew(
        agents=list(agents.values()),
        tasks=[qualify_task],
        process=Process.sequential,
        verbose=True,
    )


if __name__ == "__main__":
    crew = build_crew(brief="Qualify 100 inbound leads from a CSV export")
    print(f"Business crew ready with {len(crew.agents)} agents.")
    # result = crew.kickoff()  # enable once LLM providers are wired
