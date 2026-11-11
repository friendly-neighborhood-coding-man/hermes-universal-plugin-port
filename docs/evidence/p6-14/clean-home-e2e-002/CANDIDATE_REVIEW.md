# UVP candidate review

Source: https://github.com/anthropics/knowledge-work-plugins/tree/e605d8ddbfb688da57dfaaceebd93f12a64ef1d3/product-management @ `e605d8ddbfb688da57dfaaceebd93f12a64ef1d3`

**Candidate digest (approve this): `6a57ae419ccef2d2cf0df6da797307ebc86ae18950b30050e87ded48c0ae8b1a`**

- Original files preserved: 14 (identical to the stage: True)
- Files changed or added by UVP: 14, rules R-C001, RES-LOCAL-1
- Not installed or enabled: MCP/OAuth connectors; source commands/hooks/agents; any other plugin
- Unsupported, stays inactive (SKILLS_ONLY_PARTIAL): 16 connectors (amplitude, amplitude-eu, asana, atlassian, clickup, figma, fireflies, gmail, google calendar, intercom, linear, monday, notion, pendo, similarweb, slack); Claude MCP/OAuth connectors are not ported; Foreign host component not ported: commands
- Will install: 35 files to <home>/plugins/ported-product-management, then `hermes plugins enable ported-product-management`

## Changes

### `skills/competitive-brief/CONNECTORS.md` (RES-LOCAL-1, added)
```diff
--- stage/skills/competitive-brief/CONNECTORS.md
+++ candidate/skills/competitive-brief/CONNECTORS.md
@@ -0,0 +1,25 @@
+<!-- Modified by Universal Plugin Port (RES-LOCAL-1): copied next to the Skill so Hermes skill_view can serve it. Original: original/CONNECTORS.md (sha256 f52733eb0cd1b46f96cbf15bd9d8dd5215c9341d9323f42da076bcddccda2f5e). Apache-2.0 section 4(b) change notice. -->
+> **UVP note:** In this Hermes port the connectors described below are NOT connected (SKILLS_ONLY_PARTIAL). Treat every `~~category` as unavailable unless a Hermes tool for it is actually present.
+
+# Connectors
+
+## How tool references work
+
+Plugin files use `~~category` as a placeholder for whatever tool the user connects in that category. For example, `~~project tracker` might mean Linear, Asana, Jira, or any other tracker with an MCP server.
+
+Plugins are **tool-agnostic** — they describe workflows in terms of categories (project tracker, design, product analytics, etc.) rather than specific products. The `.mcp.json` pre-configures specific MCP servers, but any MCP server in that category works.
+
+## Connectors for this plugin
+
+| Category | Placeholder | Included servers | Other options |
+|----------|-------------|-----------------|---------------|
+| Calendar | `~~calendar` | Google Calendar | Microsoft 365 |
+| Chat | `~~chat` | Slack | Microsoft Teams |
+| Competitive intelligence | `~~competitive intelligence` | Similarweb | Crayon, Klue |
+| Design | `~~design` | Figma | Sketch, Adobe XD |
+| Email | `~~email` | Gmail | Microsoft 365 |
+| Knowledge base | `~~knowledge base` | Notion | Confluence, Guru, Coda |
+| Meeting transcription | `~~meeting transcription` | Fireflies | Gong, Dovetail, Otter.ai |
+| Product analytics | `~~product analytics` | Amplitude, Pendo | Mixpanel, Heap, FullStory |
+| Project tracker | `~~project tracker` | Linear, Asana, monday.com, ClickUp, Atlassian (Jira/Confluence) | Shortcut, Basecamp |
+| User feedback | `~~user feedback` | Intercom | Productboard, Canny, UserVoice |
```
### `skills/competitive-brief/SKILL.md` (R-C001, RES-LOCAL-1)
```diff
--- stage/skills/competitive-brief/SKILL.md
+++ candidate/skills/competitive-brief/SKILL.md
@@ -5,0 +6 @@
+<!-- Modified by Universal Plugin Port (R-C001,RES-LOCAL-1): host-semantic adaptation. Original: original/skills/competitive-brief/SKILL.md (sha256 720916695f99a70e723be02d0123908c9c968ce56e1ffdeeb423014587017cd2). Apache-2.0 section 4(b) change notice. -->
@@ -9 +10 @@
-> If you see unfamiliar placeholders or need to check which tools are connected, see [CONNECTORS.md](../../CONNECTORS.md).
+> If you see unfamiliar placeholders or need to check which tools are connected, see [CONNECTORS.md](CONNECTORS.md).
@@ -16 +17 @@
-/competitive-brief $ARGUMENTS
+/ported-product-management:competitive-brief <competitor or feature area>
```
### `skills/metrics-review/CONNECTORS.md` (RES-LOCAL-1, added)
```diff
--- stage/skills/metrics-review/CONNECTORS.md
+++ candidate/skills/metrics-review/CONNECTORS.md
@@ -0,0 +1,25 @@
+<!-- Modified by Universal Plugin Port (RES-LOCAL-1): copied next to the Skill so Hermes skill_view can serve it. Original: original/CONNECTORS.md (sha256 f52733eb0cd1b46f96cbf15bd9d8dd5215c9341d9323f42da076bcddccda2f5e). Apache-2.0 section 4(b) change notice. -->
+> **UVP note:** In this Hermes port the connectors described below are NOT connected (SKILLS_ONLY_PARTIAL). Treat every `~~category` as unavailable unless a Hermes tool for it is actually present.
+
+# Connectors
+
+## How tool references work
+
+Plugin files use `~~category` as a placeholder for whatever tool the user connects in that category. For example, `~~project tracker` might mean Linear, Asana, Jira, or any other tracker with an MCP server.
+
+Plugins are **tool-agnostic** — they describe workflows in terms of categories (project tracker, design, product analytics, etc.) rather than specific products. The `.mcp.json` pre-configures specific MCP servers, but any MCP server in that category works.
+
+## Connectors for this plugin
+
+| Category | Placeholder | Included servers | Other options |
+|----------|-------------|-----------------|---------------|
+| Calendar | `~~calendar` | Google Calendar | Microsoft 365 |
+| Chat | `~~chat` | Slack | Microsoft Teams |
+| Competitive intelligence | `~~competitive intelligence` | Similarweb | Crayon, Klue |
+| Design | `~~design` | Figma | Sketch, Adobe XD |
+| Email | `~~email` | Gmail | Microsoft 365 |
+| Knowledge base | `~~knowledge base` | Notion | Confluence, Guru, Coda |
+| Meeting transcription | `~~meeting transcription` | Fireflies | Gong, Dovetail, Otter.ai |
+| Product analytics | `~~product analytics` | Amplitude, Pendo | Mixpanel, Heap, FullStory |
+| Project tracker | `~~project tracker` | Linear, Asana, monday.com, ClickUp, Atlassian (Jira/Confluence) | Shortcut, Basecamp |
+| User feedback | `~~user feedback` | Intercom | Productboard, Canny, UserVoice |
```
### `skills/metrics-review/SKILL.md` (R-C001, RES-LOCAL-1)
```diff
--- stage/skills/metrics-review/SKILL.md
+++ candidate/skills/metrics-review/SKILL.md
@@ -5,0 +6 @@
+<!-- Modified by Universal Plugin Port (R-C001,RES-LOCAL-1): host-semantic adaptation. Original: original/skills/metrics-review/SKILL.md (sha256 e92f364b668074c72b36fd0f69a6adef2ead66640b2c17dc824c043fb613d278). Apache-2.0 section 4(b) change notice. -->
@@ -9 +10 @@
-> If you see unfamiliar placeholders or need to check which tools are connected, see [CONNECTORS.md](../../CONNECTORS.md).
+> If you see unfamiliar placeholders or need to check which tools are connected, see [CONNECTORS.md](CONNECTORS.md).
@@ -16 +17 @@
-/metrics-review $ARGUMENTS
+/ported-product-management:metrics-review <time period or metric focus>
```
### `skills/roadmap-update/CONNECTORS.md` (RES-LOCAL-1, added)
```diff
--- stage/skills/roadmap-update/CONNECTORS.md
+++ candidate/skills/roadmap-update/CONNECTORS.md
@@ -0,0 +1,25 @@
+<!-- Modified by Universal Plugin Port (RES-LOCAL-1): copied next to the Skill so Hermes skill_view can serve it. Original: original/CONNECTORS.md (sha256 f52733eb0cd1b46f96cbf15bd9d8dd5215c9341d9323f42da076bcddccda2f5e). Apache-2.0 section 4(b) change notice. -->
+> **UVP note:** In this Hermes port the connectors described below are NOT connected (SKILLS_ONLY_PARTIAL). Treat every `~~category` as unavailable unless a Hermes tool for it is actually present.
+
+# Connectors
+
+## How tool references work
+
+Plugin files use `~~category` as a placeholder for whatever tool the user connects in that category. For example, `~~project tracker` might mean Linear, Asana, Jira, or any other tracker with an MCP server.
+
+Plugins are **tool-agnostic** — they describe workflows in terms of categories (project tracker, design, product analytics, etc.) rather than specific products. The `.mcp.json` pre-configures specific MCP servers, but any MCP server in that category works.
+
+## Connectors for this plugin
+
+| Category | Placeholder | Included servers | Other options |
+|----------|-------------|-----------------|---------------|
+| Calendar | `~~calendar` | Google Calendar | Microsoft 365 |
+| Chat | `~~chat` | Slack | Microsoft Teams |
+| Competitive intelligence | `~~competitive intelligence` | Similarweb | Crayon, Klue |
+| Design | `~~design` | Figma | Sketch, Adobe XD |
+| Email | `~~email` | Gmail | Microsoft 365 |
+| Knowledge base | `~~knowledge base` | Notion | Confluence, Guru, Coda |
+| Meeting transcription | `~~meeting transcription` | Fireflies | Gong, Dovetail, Otter.ai |
+| Product analytics | `~~product analytics` | Amplitude, Pendo | Mixpanel, Heap, FullStory |
+| Project tracker | `~~project tracker` | Linear, Asana, monday.com, ClickUp, Atlassian (Jira/Confluence) | Shortcut, Basecamp |
+| User feedback | `~~user feedback` | Intercom | Productboard, Canny, UserVoice |
```
### `skills/roadmap-update/SKILL.md` (R-C001, RES-LOCAL-1)
```diff
--- stage/skills/roadmap-update/SKILL.md
+++ candidate/skills/roadmap-update/SKILL.md
@@ -5,0 +6 @@
+<!-- Modified by Universal Plugin Port (R-C001,RES-LOCAL-1): host-semantic adaptation. Original: original/skills/roadmap-update/SKILL.md (sha256 bdb121e290b590d60b94bca84d1700a8803c78db9f68f2a28fd04ccfe8aceb9e). Apache-2.0 section 4(b) change notice. -->
@@ -9 +10 @@
-> If you see unfamiliar placeholders or need to check which tools are connected, see [CONNECTORS.md](../../CONNECTORS.md).
+> If you see unfamiliar placeholders or need to check which tools are connected, see [CONNECTORS.md](CONNECTORS.md).
@@ -16 +17 @@
-/roadmap-update $ARGUMENTS
+/ported-product-management:roadmap-update <update description>
```
### `skills/sprint-planning/CONNECTORS.md` (RES-LOCAL-1, added)
```diff
--- stage/skills/sprint-planning/CONNECTORS.md
+++ candidate/skills/sprint-planning/CONNECTORS.md
@@ -0,0 +1,25 @@
+<!-- Modified by Universal Plugin Port (RES-LOCAL-1): copied next to the Skill so Hermes skill_view can serve it. Original: original/CONNECTORS.md (sha256 f52733eb0cd1b46f96cbf15bd9d8dd5215c9341d9323f42da076bcddccda2f5e). Apache-2.0 section 4(b) change notice. -->
+> **UVP note:** In this Hermes port the connectors described below are NOT connected (SKILLS_ONLY_PARTIAL). Treat every `~~category` as unavailable unless a Hermes tool for it is actually present.
+
+# Connectors
+
+## How tool references work
+
+Plugin files use `~~category` as a placeholder for whatever tool the user connects in that category. For example, `~~project tracker` might mean Linear, Asana, Jira, or any other tracker with an MCP server.
+
+Plugins are **tool-agnostic** — they describe workflows in terms of categories (project tracker, design, product analytics, etc.) rather than specific products. The `.mcp.json` pre-configures specific MCP servers, but any MCP server in that category works.
+
+## Connectors for this plugin
+
+| Category | Placeholder | Included servers | Other options |
+|----------|-------------|-----------------|---------------|
+| Calendar | `~~calendar` | Google Calendar | Microsoft 365 |
+| Chat | `~~chat` | Slack | Microsoft Teams |
+| Competitive intelligence | `~~competitive intelligence` | Similarweb | Crayon, Klue |
+| Design | `~~design` | Figma | Sketch, Adobe XD |
+| Email | `~~email` | Gmail | Microsoft 365 |
+| Knowledge base | `~~knowledge base` | Notion | Confluence, Guru, Coda |
+| Meeting transcription | `~~meeting transcription` | Fireflies | Gong, Dovetail, Otter.ai |
+| Product analytics | `~~product analytics` | Amplitude, Pendo | Mixpanel, Heap, FullStory |
+| Project tracker | `~~project tracker` | Linear, Asana, monday.com, ClickUp, Atlassian (Jira/Confluence) | Shortcut, Basecamp |
+| User feedback | `~~user feedback` | Intercom | Productboard, Canny, UserVoice |
```
### `skills/sprint-planning/SKILL.md` (R-C001, RES-LOCAL-1)
```diff
--- stage/skills/sprint-planning/SKILL.md
+++ candidate/skills/sprint-planning/SKILL.md
@@ -5,0 +6 @@
+<!-- Modified by Universal Plugin Port (R-C001,RES-LOCAL-1): host-semantic adaptation. Original: original/skills/sprint-planning/SKILL.md (sha256 c078d3f838c783e9ab53ca1a4b4c04dcd7930a55a995731b8c020cd656cb1edd). Apache-2.0 section 4(b) change notice. -->
@@ -9 +10 @@
-> If you see unfamiliar placeholders or need to check which tools are connected, see [CONNECTORS.md](../../CONNECTORS.md).
+> If you see unfamiliar placeholders or need to check which tools are connected, see [CONNECTORS.md](CONNECTORS.md).
@@ -16 +17 @@
-/sprint-planning $ARGUMENTS
+/ported-product-management:sprint-planning [sprint name or date range]
```
### `skills/stakeholder-update/CONNECTORS.md` (RES-LOCAL-1, added)
```diff
--- stage/skills/stakeholder-update/CONNECTORS.md
+++ candidate/skills/stakeholder-update/CONNECTORS.md
@@ -0,0 +1,25 @@
+<!-- Modified by Universal Plugin Port (RES-LOCAL-1): copied next to the Skill so Hermes skill_view can serve it. Original: original/CONNECTORS.md (sha256 f52733eb0cd1b46f96cbf15bd9d8dd5215c9341d9323f42da076bcddccda2f5e). Apache-2.0 section 4(b) change notice. -->
+> **UVP note:** In this Hermes port the connectors described below are NOT connected (SKILLS_ONLY_PARTIAL). Treat every `~~category` as unavailable unless a Hermes tool for it is actually present.
+
+# Connectors
+
+## How tool references work
+
+Plugin files use `~~category` as a placeholder for whatever tool the user connects in that category. For example, `~~project tracker` might mean Linear, Asana, Jira, or any other tracker with an MCP server.
+
+Plugins are **tool-agnostic** — they describe workflows in terms of categories (project tracker, design, product analytics, etc.) rather than specific products. The `.mcp.json` pre-configures specific MCP servers, but any MCP server in that category works.
+
+## Connectors for this plugin
+
+| Category | Placeholder | Included servers | Other options |
+|----------|-------------|-----------------|---------------|
+| Calendar | `~~calendar` | Google Calendar | Microsoft 365 |
+| Chat | `~~chat` | Slack | Microsoft Teams |
+| Competitive intelligence | `~~competitive intelligence` | Similarweb | Crayon, Klue |
+| Design | `~~design` | Figma | Sketch, Adobe XD |
+| Email | `~~email` | Gmail | Microsoft 365 |
+| Knowledge base | `~~knowledge base` | Notion | Confluence, Guru, Coda |
+| Meeting transcription | `~~meeting transcription` | Fireflies | Gong, Dovetail, Otter.ai |
+| Product analytics | `~~product analytics` | Amplitude, Pendo | Mixpanel, Heap, FullStory |
+| Project tracker | `~~project tracker` | Linear, Asana, monday.com, ClickUp, Atlassian (Jira/Confluence) | Shortcut, Basecamp |
+| User feedback | `~~user feedback` | Intercom | Productboard, Canny, UserVoice |
```
### `skills/stakeholder-update/SKILL.md` (R-C001, RES-LOCAL-1)
```diff
--- stage/skills/stakeholder-update/SKILL.md
+++ candidate/skills/stakeholder-update/SKILL.md
@@ -5,0 +6 @@
+<!-- Modified by Universal Plugin Port (R-C001,RES-LOCAL-1): host-semantic adaptation. Original: original/skills/stakeholder-update/SKILL.md (sha256 bcdb8ee95dc34d025dcc3d98e7435c4dca45930581b3b7a8707f8770dd364e79). Apache-2.0 section 4(b) change notice. -->
@@ -9 +10 @@
-> If you see unfamiliar placeholders or need to check which tools are connected, see [CONNECTORS.md](../../CONNECTORS.md).
+> If you see unfamiliar placeholders or need to check which tools are connected, see [CONNECTORS.md](CONNECTORS.md).
@@ -16 +17 @@
-/stakeholder-update $ARGUMENTS
+/ported-product-management:stakeholder-update <update type and audience>
```
### `skills/synthesize-research/CONNECTORS.md` (RES-LOCAL-1, added)
```diff
--- stage/skills/synthesize-research/CONNECTORS.md
+++ candidate/skills/synthesize-research/CONNECTORS.md
@@ -0,0 +1,25 @@
+<!-- Modified by Universal Plugin Port (RES-LOCAL-1): copied next to the Skill so Hermes skill_view can serve it. Original: original/CONNECTORS.md (sha256 f52733eb0cd1b46f96cbf15bd9d8dd5215c9341d9323f42da076bcddccda2f5e). Apache-2.0 section 4(b) change notice. -->
+> **UVP note:** In this Hermes port the connectors described below are NOT connected (SKILLS_ONLY_PARTIAL). Treat every `~~category` as unavailable unless a Hermes tool for it is actually present.
+
+# Connectors
+
+## How tool references work
+
+Plugin files use `~~category` as a placeholder for whatever tool the user connects in that category. For example, `~~project tracker` might mean Linear, Asana, Jira, or any other tracker with an MCP server.
+
+Plugins are **tool-agnostic** — they describe workflows in terms of categories (project tracker, design, product analytics, etc.) rather than specific products. The `.mcp.json` pre-configures specific MCP servers, but any MCP server in that category works.
+
+## Connectors for this plugin
+
+| Category | Placeholder | Included servers | Other options |
+|----------|-------------|-----------------|---------------|
+| Calendar | `~~calendar` | Google Calendar | Microsoft 365 |
+| Chat | `~~chat` | Slack | Microsoft Teams |
+| Competitive intelligence | `~~competitive intelligence` | Similarweb | Crayon, Klue |
+| Design | `~~design` | Figma | Sketch, Adobe XD |
+| Email | `~~email` | Gmail | Microsoft 365 |
+| Knowledge base | `~~knowledge base` | Notion | Confluence, Guru, Coda |
+| Meeting transcription | `~~meeting transcription` | Fireflies | Gong, Dovetail, Otter.ai |
+| Product analytics | `~~product analytics` | Amplitude, Pendo | Mixpanel, Heap, FullStory |
+| Project tracker | `~~project tracker` | Linear, Asana, monday.com, ClickUp, Atlassian (Jira/Confluence) | Shortcut, Basecamp |
+| User feedback | `~~user feedback` | Intercom | Productboard, Canny, UserVoice |
```
### `skills/synthesize-research/SKILL.md` (R-C001, RES-LOCAL-1)
```diff
--- stage/skills/synthesize-research/SKILL.md
+++ candidate/skills/synthesize-research/SKILL.md
@@ -5,0 +6 @@
+<!-- Modified by Universal Plugin Port (R-C001,RES-LOCAL-1): host-semantic adaptation. Original: original/skills/synthesize-research/SKILL.md (sha256 ae98c11102545c911a1ea5d8527be0e08a3db8e53327f2865f0db19bbb2d7e9c). Apache-2.0 section 4(b) change notice. -->
@@ -9 +10 @@
-> If you see unfamiliar placeholders or need to check which tools are connected, see [CONNECTORS.md](../../CONNECTORS.md).
+> If you see unfamiliar placeholders or need to check which tools are connected, see [CONNECTORS.md](CONNECTORS.md).
@@ -16 +17 @@
-/synthesize-research $ARGUMENTS
+/ported-product-management:synthesize-research <research topic or question>
```
### `skills/write-spec/CONNECTORS.md` (RES-LOCAL-1, added)
```diff
--- stage/skills/write-spec/CONNECTORS.md
+++ candidate/skills/write-spec/CONNECTORS.md
@@ -0,0 +1,25 @@
+<!-- Modified by Universal Plugin Port (RES-LOCAL-1): copied next to the Skill so Hermes skill_view can serve it. Original: original/CONNECTORS.md (sha256 f52733eb0cd1b46f96cbf15bd9d8dd5215c9341d9323f42da076bcddccda2f5e). Apache-2.0 section 4(b) change notice. -->
+> **UVP note:** In this Hermes port the connectors described below are NOT connected (SKILLS_ONLY_PARTIAL). Treat every `~~category` as unavailable unless a Hermes tool for it is actually present.
+
+# Connectors
+
+## How tool references work
+
+Plugin files use `~~category` as a placeholder for whatever tool the user connects in that category. For example, `~~project tracker` might mean Linear, Asana, Jira, or any other tracker with an MCP server.
+
+Plugins are **tool-agnostic** — they describe workflows in terms of categories (project tracker, design, product analytics, etc.) rather than specific products. The `.mcp.json` pre-configures specific MCP servers, but any MCP server in that category works.
+
+## Connectors for this plugin
+
+| Category | Placeholder | Included servers | Other options |
+|----------|-------------|-----------------|---------------|
+| Calendar | `~~calendar` | Google Calendar | Microsoft 365 |
+| Chat | `~~chat` | Slack | Microsoft Teams |
+| Competitive intelligence | `~~competitive intelligence` | Similarweb | Crayon, Klue |
+| Design | `~~design` | Figma | Sketch, Adobe XD |
+| Email | `~~email` | Gmail | Microsoft 365 |
+| Knowledge base | `~~knowledge base` | Notion | Confluence, Guru, Coda |
+| Meeting transcription | `~~meeting transcription` | Fireflies | Gong, Dovetail, Otter.ai |
+| Product analytics | `~~product analytics` | Amplitude, Pendo | Mixpanel, Heap, FullStory |
+| Project tracker | `~~project tracker` | Linear, Asana, monday.com, ClickUp, Atlassian (Jira/Confluence) | Shortcut, Basecamp |
+| User feedback | `~~user feedback` | Intercom | Productboard, Canny, UserVoice |
```
### `skills/write-spec/SKILL.md` (R-C001, RES-LOCAL-1)
```diff
--- stage/skills/write-spec/SKILL.md
+++ candidate/skills/write-spec/SKILL.md
@@ -5,0 +6 @@
+<!-- Modified by Universal Plugin Port (R-C001,RES-LOCAL-1): host-semantic adaptation. Original: original/skills/write-spec/SKILL.md (sha256 ca6670913878b4ac4582727562bfced5271492a5a800d934f68c9e7bc1cd4dcc). Apache-2.0 section 4(b) change notice. -->
@@ -9 +10 @@
-> If you see unfamiliar placeholders or need to check which tools are connected, see [CONNECTORS.md](../../CONNECTORS.md).
+> If you see unfamiliar placeholders or need to check which tools are connected, see [CONNECTORS.md](CONNECTORS.md).
@@ -16 +17 @@
-/write-spec $ARGUMENTS
+/ported-product-management:write-spec <feature or problem statement>
```
