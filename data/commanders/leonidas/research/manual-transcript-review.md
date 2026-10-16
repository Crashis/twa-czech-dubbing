# Leonidas — manual transcript review

Audio references below are relative to the private archive root. The candidate is not an approved final transcript. No human listening is recorded.

## Media ID 12766875

- Candidate English: We have been damaged by friendly fire!
- Resolution: NEEDS_MANUAL_WORDING_VERIFICATION; confidence: MEDIUM
- Category/trigger: BATTLE_EVENT; battle event: your units are damaged by allied stakes
- Original duration/size: 2.10471875 s / 20156 B
- Context: battle_vo_announcer.bnk; Event 4168474204; container 215717646; Sound 463949289
- Decision path: vo_actor=Commander_Leonidas (659903553); battle_event_group_636323490=deployables_ff_stakes_receive (733485138)
- Evidence: CONTEXT_CORRECTION: Largest local model gives this wording in both original and +0.5s/beam10 analysis; smaller models say Were being. Tense remains explicitly uncertain.; RAW: base.en: "We're being damaged by friendly fire!"; small.en: "We're being damaged by friendly fire!"; medium.en: 'We have been damaged by friendly fire!'; alternative local ASR: [{"source": "asr-alternative-medium-leading.json", "model": "medium.en-leading", "leading_silence_seconds": 0.5, "beam_size": 10, "text": "We have been damaged by friendly fire!", "avg_logprob": -0.18396271599663627, "no_speech_prob": 0.0786568745970726}]
- Archive WAV: `commander-research/leonidas/decoded-wav/12766875.wav`
