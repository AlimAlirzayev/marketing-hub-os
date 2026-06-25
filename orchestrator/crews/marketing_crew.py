"""Xalq Insurance Digital OS - Marketing crew.

Six agents covering the marketing domain. Skeleton: agent definitions and one
example task are real; LLM wiring is delegated to ``router.get_llm`` and left
as TODO. Run ``build_crew`` once providers are configured.
"""

from __future__ import annotations

from crewai import Agent, Crew, Process, Task

# Each agent declares its preferred routing tier; the orchestrator resolves
# the tier to a concrete LLM via orchestrator/router.py.
AGENT_TIERS: dict[str, str] = {
    "trend_researcher": "free_bulk",   # Gemini - high-volume scraping
    "content_writer": "complex",       # Claude - best copy quality
    "visual_creator": "free_bulk",     # Gemini - prompt generation for images
    "social_scheduler": "fast",        # Groq - quick scheduling decisions
    "analytics_tracker": "fast",       # Groq - fast metric crunching
    "email_campaign": "complex",       # Claude - personalized email copy
    "video_editor": "complex",         # Claude - precise edit-spec authoring
}


def build_agents() -> dict[str, Agent]:
    """Construct the six marketing agents."""
    trend_researcher = Agent(
        role="Trend Researcher",
        goal="Find emerging marketing trends across X, TikTok, and LinkedIn daily",
        backstory=(
            "A relentless digital scout who tracks viral content patterns and "
            "surfaces what audiences will care about next week, not last week."
        ),
        verbose=True,
        allow_delegation=False,
    )
    content_writer = Agent(
        role="Content Writer",
        goal="Write high-converting blog posts, social copy, and ad creatives",
        backstory=(
            "A senior copywriter who turns raw trend data into on-brand content "
            "that reads naturally and drives engagement."
        ),
        verbose=True,
        allow_delegation=False,
    )
    visual_creator = Agent(
        role="Visual Creator",
        goal="Generate image prompts and briefs for social media visuals",
        backstory=(
            "An art director who translates campaign concepts into precise "
            "image-generation prompts and infographic layouts."
        ),
        verbose=True,
        allow_delegation=False,
    )
    social_scheduler = Agent(
        role="Social Scheduler",
        goal="Plan optimal posting times and assemble the publishing calendar",
        backstory=(
            "A data-driven planner who knows when each platform's audience is "
            "most active and sequences content for maximum reach."
        ),
        verbose=True,
        allow_delegation=False,
    )
    analytics_tracker = Agent(
        role="Analytics Tracker",
        goal="Measure engagement, compute ROI, and flag underperforming content",
        backstory=(
            "A performance analyst who closes the loop by turning campaign "
            "results into concrete recommendations."
        ),
        verbose=True,
        allow_delegation=False,
    )
    email_campaign = Agent(
        role="Email Campaign Manager",
        goal="Design drip campaigns and personalized email sequences",
        backstory=(
            "An email marketing specialist who builds segmented, personalized "
            "sequences that nurture leads without feeling automated."
        ),
        verbose=True,
        allow_delegation=False,
    )
    video_editor = Agent(
        role="Video Editor",
        goal=(
            "Turn raw recordings into platform-ready clips by authoring an "
            "edit spec for the Video Studio renderer"
        ),
        backstory=(
            "A short-form video producer who plans cuts, pacing, captions, and "
            "motion graphics. Never touches the footage directly: writes a "
            "precise edit_spec.json (see video-studio/edit_spec.schema.json) "
            "that render.py executes deterministically with FFmpeg + Remotion."
        ),
        verbose=True,
        allow_delegation=False,
    )
    return {
        "trend_researcher": trend_researcher,
        "content_writer": content_writer,
        "visual_creator": visual_creator,
        "social_scheduler": social_scheduler,
        "analytics_tracker": analytics_tracker,
        "email_campaign": email_campaign,
        "video_editor": video_editor,
    }


def build_crew(brief: str) -> Crew:
    """Assemble the marketing crew for a given campaign brief.

    TODO: attach LLMs via router.get_llm before running in production.
    """
    agents = build_agents()

    research_task = Task(
        description=(
            f"Research current trends relevant to this campaign brief: {brief}. "
            "Return the top 5 trends with a one-line rationale each."
        ),
        expected_output="A ranked list of 5 trends with rationales.",
        agent=agents["trend_researcher"],
    )

    return Crew(
        agents=list(agents.values()),
        tasks=[research_task],
        process=Process.sequential,
        verbose=True,
    )


if __name__ == "__main__":
    crew = build_crew(brief="Promote a zero-budget AI automation course")
    print(f"Marketing crew ready with {len(crew.agents)} agents.")
    # result = crew.kickoff()  # enable once LLM providers are wired
