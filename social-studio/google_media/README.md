# Google Media Opportunity Layer

This is the governed bridge between Social Studio and Google's user-facing
Gemini media surfaces. It never stores an API key. One evidence-locked campaign
object becomes paste-ready handoffs for Canvas, Nano Banana, Gemini Omni/Veo,
Lyria, Audio Studio voice-over, and Audio Overview.

No command here calls an external API, publishes, signs in, or spends money.
Every package is `draft_only`.

## Use

```powershell
python social-studio\google_media\planner.py doctor
python social-studio\google_media\planner.py validate social-studio\google_media\campaign.example.json
python social-studio\google_media\planner.py build social-studio\google_media\campaign.example.json
```

The build lands at `social-studio/output/<slug>/google-media/`. In Gemini
Canvas use **Add Gemini features**, never an API key or raw browser fetch. Use
only public, synthetic, or approved campaign data. Generate two text concepts,
select one, then use the relevant medium handoff. Return the package to Ramin-OS
for review and approval.

Shared Canvas storage is not an internal team database. Never put customer,
claim, policy, credential, payment, or private strategy data in it.
