# Third-party provenance

The PACK index XOR layout was cross-checked against RPFM `cbc9626d098dc645f40ba950be2d90c60ea94805`, `rpfm_lib/src/encryption/mod.rs`, by Ismael Gutiérrez González and contributors. Its MIT notice is preserved in [third_party/RPFM-MIT.txt](third_party/RPFM-MIT.txt).

Arena extended PFH5 field interpretation was compared with TotalWar-Modding/tw_pack_lib `7a9d2264e1b4ea0f35e9332d00dd9a870abdb65d`, `src/parse.rs` and `src/crypto.rs`. No upstream Rust binary or source checkout is distributed here. The project retains its Python parser and mandatory public-key signature verification.

WEM structure was researched using ww2ogg 0.24 (`14ed9b0dd62e815a38702b5f03c57006cbe2501b`) and vgmstream's Wwise parser (`7c520e8f9b078dfde2f84f1b5bcbad0c6c415806`). Bank XML is produced separately by wwiser. This repository supplies its Python inspection/workflow tools; those third-party decoders, bank dumpers and codebook binaries must be obtained separately.

The development workflow used pas2k/wav2wem `38e916953bec63862b13b449d780d1303a1bf29c`. Its README declares GPLv2 and explains its embedded GPL oggenc2 binary. Neither that binary, embedded assets nor its checkout are included. Obtain and build it from upstream with its notices. Tool download/build provenance and hashes are recorded in `docs/DEVELOPMENT.md`.

No original game audio, bank or complete PACK is distributed by this repository. The stored RSA public verification key is verification data; it is not a private signing key.

The Windows installer bundles CPython and Tcl/Tk using PyInstaller 6.22.3. PyInstaller is GPL-2.0-or-later with its bootloader distribution exception; see its [official license](https://pyinstaller.org/en/stable/license.html). Release bundles include the full PyInstaller, Python, Tcl/Tk and RPFM license texts in `licenses/`. PyInstaller and its build dependencies are obtained separately in the ignored development environment; no third-party tool binaries are source candidates.

The Tcl 8.6.15 license is retained from [tcltk/tcl core-8-6-15](https://github.com/tcltk/tcl/blob/core-8-6-15/license.terms) in [third_party/Tcl-8.6.15.txt](third_party/Tcl-8.6.15.txt), since the Python Windows runtime does not ship it alongside its Tcl script library. Recheck the license and runtime versions when changing the pinned Python toolchain.

Optional offline voice research uses separately installed faster-whisper 1.2.1 (MIT), CTranslate2, PyAV and NumPy, with separately obtained Whisper model weights. Their packages, native libraries, caches and model weights are not distributed here. Keep the notices supplied by those distributions in the private research environment. `requirements-research.txt` records the versions used; the public source audit records model/tool hashes. No transcription service or TTS client is bundled in this workflow.
