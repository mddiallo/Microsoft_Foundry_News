# Microsoft Foundry — Daily News Digest

**Date:** June 10, 2026

> A roundup of the latest Microsoft Foundry news, drawn from Microsoft Build 2026 coverage and official updates. The overarching theme: Foundry is moving from experimental to **production-ready**, making AI agents first-class citizens with a full runtime, memory, enterprise/web access, and rigorous governance.

---

## 1. Production Runtime for Agents

- **Hosted Agents** are reaching general availability with sandboxed, **hypervisor-isolated** sessions, persistent state, direct filesystem access, and source-code deployment via the Azure Developer CLI.
- Per-agent **Entra ID** identity, built-in content safety, **Voice Live** and WebSocket support.
- Compatible with **Microsoft Agent Framework, GitHub Copilot SDK, LangGraph**, and others — no major rewrites needed.
- **Foundry Agent Framework 1.0** is now generally available (stable orchestration, lifecycle management).
- **Agent Control Specification (ACS)** is in preview for deterministic runtime controls and governance.
- General availability for the production hosted-agent service is expected by **July 2026**.

## 2. Model Catalog Expansion

- **11,000–12,000+ models** now available (Microsoft, OpenAI, Anthropic, NVIDIA, Fireworks AI).
- **Fireworks AI** generally available; **OpenAI GPT-5.5** and **Anthropic Claude Opus 4.8** in preview.
- New **MAI (Microsoft AI)** models:
  - **MAI-Thinking-1** — enterprise-grade reasoning (private preview)
  - **MAI-Code-1-Flash** — code, rolling out in VS Code
  - **MAI-Image-2.5** — image generation
  - **MAI-Voice-2** — voice
  - **MAI-Transcribe-1.5** — transcription
- Improved performance, larger context windows, and lower costs; support for fine-tuning and managed compute.

## 3. Foundry IQ, Memory & Knowledge

- **Foundry IQ** serves as a unified **knowledge plane**, connecting enterprise and web knowledge for agentic retrieval — reducing custom RAG plumbing.
- Expands to **serverless retrieval** and easy connection to multiple knowledge sources.
- **Agent memory** (public preview): procedural, user, and session memory.
- **Web IQ** enables real-time web grounding, ~2.5x faster than alternatives.

## 4. Toolbox, Integration & Voice

- **Foundry Toolkit for VS Code** is now generally available — faster agent development.
- **Toolboxes** (public preview) centralize tools, skills, MCP clients, and enterprise data through a governed endpoint (web/code search, OpenAPI tools, Azure AI Search, agent-to-agent connections).
- **Model Context Protocol (MCP)** is now the default integration layer across Microsoft's stack (Teams SDK, Copilot, Agent 365, and more).
- Foundry agents can **one-click publish** to **Microsoft Teams** and **Microsoft 365 Copilot** (GA June 2026).
- **Voice Live API** (available): real-time recognition, text-to-speech, interruption, and avatars.

## 5. Trust, Governance & Observability

- New evaluation and safety tooling: **ASSERT, Agent Control Specification, Guided Guardrail Setup, Rubric, Agent Optimizer, Agent ROI**.
- Tracing and observability for production monitoring and regulatory compliance.
- Policy-driven, deterministic run-time controls bring safety and testing closer to the developer loop.

## 6. New Product — Microsoft Scout

- **Microsoft Scout**, the first **"autopilot" agent** — an always-on autonomous agent with its own identity.
- In preview for **Windows and Mac** as part of a new agent-first hardware and OS/runtime stack.

---

## Strategic Takeaways

- Focus has shifted from raw model capability to **reliability, governability, and practical production deployment**.
- **MCP** is now the common "language" for agents across the ecosystem, reducing integration friction.
- AI agents are evolving from simple assistants into **autonomous systems** with memory, tool-use, and integrated business workflows.

## What's Next

- Hosted Agents reach **GA in July 2026**.
- One-click publishing to Teams / M365 Copilot by **June 2026**.
- More models and hardware integrations rolling out through the summer.

---

## Sources

- [What's new in Microsoft Foundry | Build Edition — Microsoft DevBlogs](https://devblogs.microsoft.com/foundry/whats-new-in-microsoft-foundry-build-2026/)
- [Announcing 3 new world-class MAI models, available in Foundry — microsoft.ai](https://microsoft.ai/news/today-were-announcing-3-new-world-class-mai-models-available-in-foundry/)
- [With Foundry, Microsoft bets the enterprise AI battle is about agents — The New Stack](https://thenewstack.io/microsoft-foundry-build-2026-ai-agents/)
- [Microsoft Build 2026: MCP and the Agent Stack — arcade.dev](https://www.arcade.dev/blog/microsoft-build-2026-agent-stack/)
- [Microsoft Build 2026 Recap — All AI Announcements — aguidetocloud.com](https://www.aguidetocloud.com/blog/microsoft-build-2026-recap/)
- [Microsoft Build 2026 recap — testingcatalog.com](https://www.testingcatalog.com/microsoft-build-2026-recap-from-windows-to-copilot-all-ai/)
- [Everything Microsoft Announced at Build 2026 — The Neuron](https://www.theneuron.ai/explainer-articles/everything-microsoft-announced-at-microsoft-build-2026-explained/)
- [microsoft/Build26-news — GitHub](https://github.com/microsoft/Build26-news/blob/main/news.md)

*Generated June 10, 2026. Headlines are drawn from publicly reported coverage; verify specifics against official Microsoft sources before relying on them.*
