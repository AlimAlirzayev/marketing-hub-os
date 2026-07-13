# Ramin-OS Notion Worker

Use the root Ramin-OS rules plus `AGENTS.md` in this folder. This worker is a
draft/read-only Notion Custom Agent helper. Do not read `.env` or handle tokens.

Useful local checks:

```powershell
npm run check
ntn workers exec screenRaminOsAction --local --no-dotenv -d '{"action":"draft ideas","target":null,"publicFacing":false,"sendsMessage":false,"changesProduction":false,"deletesOrArchives":false,"spendsMoney":false,"containsSecrets":false,"containsCustomerData":false,"containsClaimsOrPolicies":false}'
```

Deploy/login/env commands require a human checkpoint.
