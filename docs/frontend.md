> OUTDATED / SUPERSEDED: exploratory design concept. Production status, performance claims, forensic guarantees, and listed features are not implementation evidence. See [implementation plan](implementation_plan.md).

# Project Brief & Product Requirements Document (PRD)
## Project: VeritasScope (VERITAS//ANALYTICS)
**Version:** 1.0.0  
**Classification:** Open Source Intelligence (OSINT) & Defense-Grade Cognitive Forensics  
**Status:** In Production / Design Specification Verified  
**Document Author:** Stitch AI System Architecture & UX Practice

---

## 1. Executive Summary & Problem Statement

### 1.1 Context
In the modern information ecosystem, state-sponsored actors, algorithmic content mills, and astroturfed proxy networks deploy high-velocity cognitive distortion campaigns. Traditional fact-checking is slow (hours to days), manual, ideologically vulnerable, and incapable of matching the speed of automated narrative proliferation.

### 1.2 The Problem
1. **Multi-Vector Manipulation:** Disinformation rarely relies solely on textual falsehoods; it blends doctored metadata, deepfake synthetic audio/video, selective framing, cognitive bias exploitation, and coordinated synthetic bot swarms.
2. **Speed & Volume:** Ingesting and evaluating thousands of cross-border narratives per minute requires deterministic, algorithmic screening.
3. **Lack of Explainability & Trust:** Black-box AI detectors fail to provide defensible evidence, forensic provenance, or transparent criteria weighting.

### 1.3 The Solution: VeritasScope
VeritasScope is an intelligence-grade propaganda forensic engine designed for investigative journalists, defense analysts, intelligence watchdesks, and enterprise trust & safety teams. It accepts raw URLs, files, transcripts, or batch feeds, decomposes them against a 7-tier standardized criteria codex, anchors findings in cryptographic provenance (C2PA / SHA-256), and traces narrative amplification across social topologies.

---

## 2. Product Goals & Core Metrics (KPIs)

| Objective | Key Result (KR) | Target SLA / Metric |
| :--- | :--- | :--- |
| **Ingestion Latency** | Time elapsed from target submission to initial verdict | < 2.5 seconds (Standard Rapid Scan) |
| **False Positive Ceiling** | False positive rate on verified clean investigative journalism | < 0.38% (Audited Heuristic Threshold) |
| **Multi-Modal Coverage** | Support text, PDFs, audio spectrograms, video clips, and web articles | 100% parity across top 5 narrative vectors |
| **Cryptographic Provenance** | Tamper-proof chain-of-custody for court & news syndication | SHA-256 integrity + C2PA manifest export |
| **Analytical Rigor** | Explainability of risk score | 100% of flags linked to reproducible forensic criteria |

---

## 3. Target Personas & Use Cases

### Persona A: The Investigative Journalist / Newsroom Fact-Checker
* **Profile:** Works at an international news syndicate or independent fact-checking bureau (IFCN / EDMO aligned).
* **Pain Points:** Overwhelmed by leaked documents, deceptive press releases, and spoofed whistleblowers. Needs fast verification with exportable PDF dossiers.
* **Key Workflow:** Submits suspicious document -> Reviews Annotated Forensic Telemetry pane -> Exports C2PA cryptographically signed verification certificate.

### Persona B: Cyber Threat Intelligence (CTI) & Defense Analyst
* **Profile:** Monitored national security or defense cyber-command watchdesk.
* **Pain Points:** Coordinated Inauthentic Behavior (CIB) across state proxy networks (e.g., Operation Doppelgänger, Ghostwriter).
* **Key Workflow:** Monitors Live Threat Intel Feed -> Traces topological propagation blast radius -> Isolates bot swarm seed clusters -> Dispatches tactical defense advisories.

### Persona C: Platform Trust & Safety (T&S) Policy Officer
* **Profile:** Enterprise or social platform risk engineer.
* **Pain Points:** Calibrating algorithmic moderation thresholds without incurring partisan censorship bias.
* **Key Workflow:** Uses the Dynamic Criteria Weight Calibration Sandbox -> Simulates threshold responses against synthetic media vs bot swarms -> Deploys strictness policies.

---

## 4. System Architecture & High-Level Information Architecture

```
                                [ INPUT VECTORS ]
        ┌───────────────────┬───────────────────┬───────────────────┐
      URL Link         File Dropzone        Raw Payload       OSINT Batch Feed
        └─────────┬─────────┴─────────┬─────────┴─────────┬─────────┘
                  │                   │                   │
                  ▼                   ▼                   ▼
     ┌─────────────────────────────────────────────────────────────┐
     │           VERITAS MULTI-MODAL INGESTION CONSOLE             │
     │      (EXIF Parser / Styliometry / Spectrogram / OCR)        │
     └──────────────────────────────┬──────────────────────────────┘
                                    │
                                    ▼
     ┌─────────────────────────────────────────────────────────────┐
     │        4-STAGE NEURAL COGNITIVE FORENSIC PIPELINE           │
     │  Stage 1: Semantic & Valence Extraction (Affective Pacing)   │
     │  Stage 2: Fallacy Pattern Matching (14 Formalized Fallacies) │
     │  Stage 3: Attribution & Coordinated Propagation Graph       │
     │  Stage 4: Epistemic Audit Certificate & Cryptographic Proof │
     └──────────────────────────────┬──────────────────────────────┘
                                    │
                                    ▼
     ┌─────────────────────────────────────────────────────────────┐
     │          7-TIER HEURISTIC PROPAGANDA TAXONOMY               │
     │  [18% Emotional Manipulation]  [20% Fabricated Authority]    │
     │  [15% Logical Fallacies]       [16% Epistemic Distortion]   │
     │  [14% Coordinated Echoing]     [12% Narrative Playbooks]    │
     │  [05% Linguistic Urgency & Virality Engineering]            │
     └──────────────────────────────┬──────────────────────────────┘
                                    │
                  ┌─────────────────┴─────────────────┐
                  ▼                                   ▼
   ┌─────────────────────────────┐     ┌─────────────────────────────┐
   │  INSPECTION DOSSIER REPORT  │     │   LIVE THREAT INTEL FEED    │
   │  - Synthetic Risk Gauge     │     │   - Global Firehose Stream  │
   │  - In-Text Annotation Pane  │     │   - Propagation Radar       │
   │  - Blast Radius Topology    │     │   - Origin Geo-Anchor Map   │
   │  - Audit Chain & C2PA Proof │     │   - Multi-Vector Filtering  │
   └─────────────────────────────┘     └─────────────────────────────┘
```

---

## 5. Detailed Functional Specifications by Module

### Module 1: Ingestion Engine (`Ingestion Engine - VeritasScope Propaganda Scanner`)
* **Multi-Modal Input Bar:**
  * Auto-detect protocol for URLs (Web crawlers, Telegram channel links, YouTube/TikTok clips).
  * Direct file drag-and-drop supporting PDF, DOCX, MP4, MP3 with 2.5 GB ceiling.
  * Raw text payload and batch JSON/CSV ingestion APIs.
* **Scan Profile Selector:**
  * **L1 Rapid Scan:** ~1.2s baseline scan focusing on linguistic lexical tension and affective triggers.
  * **L2 Deep Forensic:** ~4.8s deep scan with narrative co-occurrence graphs and socket puppet detection (Recommended default).
  * **L3 Threat APT Profiling:** ~12.0s exhaustive scan cross-referencing known disinformation playbooks (Doppelgänger, Ghostwriter, Secondary Infektion).
* **Epistemic Strictness Matrix:**
  * Presets: *Press Standard*, *OSINT Baseline*, *Academic Peer*.
  * Interactive sliders for Rhetorical Drift Sensitivity and Synthetic Consensus Tolerance.
* **Instant Intercept Samples:** Quick-load test fixtures demonstrating 89% synthetic forgery, 74% astroturf op-ed, and 96% verified authentic organic articles.

### Module 2: The 7-Axis Forensic Criteria Matrix (`Forensic Criteria Matrix - VeritasScope`)
1. **Emotional Manipulation & Fear-Mongering (Weight: 18%)**
   * *Telemetry:* High affective valence, catastrophe thresholds, rage-priming metrics, somatic cueing.
2. **Source Obfuscation & Fabricated Authority (Weight: 20%)**
   * *Telemetry:* Recursive circular citations, anonymous "whistleblower" claims, Levenshtein distance on institutional impersonation.
3. **Logical Fallacies & Cognitive Biases (Weight: 15%)**
   * *Telemetry:* Formalized taxonomy of Whataboutism, False Dichotomies, Ad Hominem diversions, Strawman constructions.
4. **Epistemic Distortion & Selective Framing (Weight: 16%)**
   * *Telemetry:* Intentional omissions of counter-evidence, chronological re-sequencing, out-of-context audio/video clips.
5. **Coordinated Synthetic Echoing (Weight: 14%)**
   * *Telemetry:* Sub-340ms timestamp delta across independent domain clusters, identical copypasta payloads, cross-platform seeding.
6. **Narrative Disinformation Playbook Alignment (Weight: 12%)**
   * *Telemetry:* Attribution signatures against known APT state campaigns (Storm-1099, Operation Doppelgänger).
7. **Linguistic Urgency & Virality Engineering (Weight: 5%)**
   * *Telemetry:* Coercive virality hooks ("Retweet before deleted"), Us-vs-Them in-group/out-group polarizing syntax.
* **Simulation Sandbox:** Real-time formula recalculation:
  $$R_{veritas} = 100 \times \left[ \frac{1}{1 + \exp(-k \times (\sum (w_i \cdot c_i) - \theta))} \right]$$
  Allows risk teams to evaluate sensitivity curves before deployment.
* **International Governance Compliance:** Benchmarked against UN A/HRC/47/25, EU Code of Practice on Disinformation (EDMO), and Harvard Shorenstein Media Manipulation Casebook.

### Module 3: Inspection Report Dossier (`Inspection Report Dossier - VeritasScope`)
* **Synthetic Deception Assessment Header:** Grade score (e.g., `88/100 FAIL: GRADE F`), attribution cluster tag, and real-time viral propagation signal pulse.
* **Seven-Axis Diagnostic Meter:** Micro-visualizations displaying granular sub-scores across each criteria vector.
* **Annotated Forensic Telemetry Pane:**
  * In-line highlights categorization:
    * Crimson: Doctored Fact / Fabrication
    * Amber: Emotional Trigger / Rage Bait
    * Purple: Anonymous / Unverified Fake Source
    * Cyan: Wire Mirroring / Copypasta
* **Forensic Drilldown & Counter-Evidence Sandbox:**
  * Side-by-side counter-evidence citations (e.g., Copernicus Sentinel-2 satellite imagery, official utility grid logs).
  * Error Level Analysis (ELA) on embedded imagery proving Photoshop manipulation.
  * Ethereum / Sepolia cryptographic provenance ledger verification.
* **Network Amplification Blast Radius:**
  * Topological infection graph showing initial seed accounts, Discord/Telegram bridges, and automated repeater clusters.
* **Chronological Audit Chain:** Immutable tabular log of every forensic detection vector for legal submission.

### Module 4: Live Threat Intel Feed (`Live Threat Intel Feed - VeritasScope`)
* **Global Content Ingestion Firehose:** Continuously streaming analyzed articles, tweets, and wire dispatches with instant status badges (*Confirmed Propaganda*, *Deepfake Manipulated*, *Suspicious*, *Verified Clean*).
* **Tactical Propagation Radar:** Polar coordinate radar mapping amplitude and cross-seeding frequency of active narrative clusters.
* **Primary Origin Anchor Map:** Geographic triangulation of server infrastructure, IP convergence nodes, and relay corridors.
* **Macro Threat Telemetry Cards:** Active campaigns count, ingestion velocity (18,420 items/hr), bot clusters neutralized, and average latency (3.2s).

---

## 6. Technical Stack & Implementation Architecture

* **Frontend:** Single-Page Web Application, Tailwind CSS design system, High-contrast Dark Forensic Theme (`#0b1326` background, `#06b6d4` cyan primary, `#ef4444` threat red, `#f59e0b` caution amber).
* **Styling & Design System Tokens:** Plus Jakarta Sans & JetBrains Mono typography, custom SVG telemetry radars, canvas-based node topological infection graphs.
* **Data Integrity & Cryptography:** C2PA metadata wrapper, SHA-256 content hashes, decentralized provenance ledger anchoring.
* **Engine Integration:** Multi-modal Heuristic Engine v4.9b with heuristic parsers for OpenGraph, EXIF, and NLP sentiment tensors.

---

## 7. Roadmap & Future Iterations

* **Q3 2025:** Browser Extension for on-the-fly newsroom & social feed verification.
* **Q4 2025:** Real-time synthetic voice cloaking & deepfake phone stream audio interception.
* **Q1 2026:** Automated counter-narrative inoculation dispatch integration via certified fact-checking syndicates.
