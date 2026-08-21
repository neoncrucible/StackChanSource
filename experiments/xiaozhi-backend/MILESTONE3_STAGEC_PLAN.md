# Kadence 2.0 Alpha 2 — Milestone 3 Stage C Plan

Status: **READY FOR PHYSICAL A/B**

Date: **21 Aug 2026**

Branch: `kadence/2.0-alpha-2`

## Goal

Compare Gemini 3.5 Flash-Lite and GPT-5.6 Luna through the complete physical Kadence voice pipeline without telling the human operator which provider is active.

Stage C does **not** retune transport, ASR, endpointing, TTS, robot lifecycle, expressions, LEDs, or firmware. The LLM remains the only intended model variable.

## Blind mechanism

`m3_stage_c_windows.ps1` creates a local-only Stage C session and randomly maps the two providers to labels **A** and **B**. The real mapping is written only to the local run folder as `blind_mapping.json`.

While a Stage C session is active, Control Surface V4.2 masks model/provider identity in visible health labels and the live log. Raw server logs are still retained under the local Stage C run folder for later timing analysis; the operator should not open those raw logs until the blind judgement is locked.

The ordinary Control Surface is unchanged when no Stage C session is active.

## Physical prompt pack

Speak the same five prompts to profile A and profile B, in this order and as naturally/consistently as practical:

1. **Who are you?**
2. **What is forty-six times nineteen? Reply with only the number.**
3. **Explain what a VPN does in one sentence.**
4. **My Windows PC says it is connected to Wi-Fi but has no internet. Give me the first two checks, concise.**
5. **I forgot to plug in the monitor and now the screen is black. Diagnose the problem.**

Arithmetic target for prompt 2: **874**.

## Human judgement

Judge A and B separately on:

- perceived responsiveness / thinking delay;
- answer usefulness / correctness;
- canonical Kadence personality;
- spoken concision;
- instruction following;
- overall preference.

Do not use the raw logs or mapping to influence the human choice.

## Timing evidence

For each profile the raw server log should retain the existing physical markers where available:

- Silero endpoint request timing;
- ASR completion after commit;
- final transcript;
- LLM-to-TTS first spoken segment timing visible in normal server logging;
- provider/profile startup evidence for later unmasking.

The human perceived-latency judgement is evaluated alongside those retained markers rather than replaced by them.

## Procedure

1. Stop the Kadence server / close the active Control Surface server process.
2. Run `m3_stage_c_windows.ps1 -Action New`. This creates the blind session and arms profile A.
3. Open the normal Kadence Control Surface, power the robot, start the server, and run all five prompts.
4. Stop the server and close the Control Surface.
5. Run `m3_stage_c_windows.ps1 -Action B`.
6. Re-open the normal Control Surface and run the exact same five prompts.
7. Stop the server and lock the human A/B judgement before revealing the mapping.
8. Upload the Stage C `A-server.log`, `B-server.log`, and `blind_mapping.json`, together with the human preference notes.
9. After analysis, run `m3_stage_c_windows.ps1 -Action Reset` to restore the saved pre-boot profile and remove blind UI mode.

Do not run `-Action Reveal` until the human judgement is locked.

## Gate

Stage C passes when:

- both blind profiles complete the matched physical prompt set;
- no Alpha 1 transport regression appears;
- responses are usable and canonical;
- physical timing evidence is retained;
- the human blind preference is recorded before provider reveal;
- Stage B and Stage C evidence together support an explicit Alpha 2 default-provider decision.
