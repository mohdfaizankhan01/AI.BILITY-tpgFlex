<div align="center">

# tpgFlex Accessible Voice Booking Assistant

### An AI and Crowdsourcing Approach to Inclusive Public Transport in Geneva

**Course:** Crowdsourcing and AI
**Professor:** François Grey
**Teaching Assistant:** Saray Quirant Perez

**Team:** [Team Member 1], [Team Member 2], [Team Member 3], [Team Member 4]

**Date:** [Submission date]
**Institution:** [University name]
**GitHub repository:** [GITHUB_REPO_LINK]

</div>

---

## Abstract

This report documents the design and implementation of an accessibility and inclusion layer for tpgFlex, the on-demand shared minibus service operated in the canton of Geneva. The work was carried out in response to Problem Statement #4 of the Crowdsourcing and AI course, which asked how the current tpgFlex application could be made more accessible and inclusive. Starting from a baseline voice-booking assistant, four contributions were developed: a multi-sensor blind navigation layer combining camera, GPS, compass, step counting, and spatial audio; a two-tier crowdsourcing layer pairing one-time human stop surveys with continuous passive mobile sensing, aggregated through a trust-weighted, temporally decaying evidence model; an Epicollect-based field survey feeding a rule-based evaluator that produces five user-facing stop scores; and a profile-based personalization system that adapts both scoring and interface to six user types. Requirements were grounded in field visits to two organizations supporting people with disabilities. The project demonstrated that profile-aware accessibility scoring yields materially different evaluations of the same stop for different users, that on-device machine learning is sufficient for last-metre navigation in demonstration conditions, and that a free, local-first technology stack can deliver these capabilities at zero marginal cost.

---

## Table of Contents

- [1. Introduction](#1-introduction)
- [2. Background and Related Work](#2-background-and-related-work)
- [3. User Research and Stakeholder Engagement](#3-user-research-and-stakeholder-engagement)
- [4. System Overview](#4-system-overview)
- [5. Epicollect Crowdsourced Survey Methodology](#5-epicollect-crowdsourced-survey-methodology)
- [6. Crowdsource and AI Layer](#6-crowdsource-and-ai-layer)
- [7. Rule-Based Stop Evaluation](#7-rule-based-stop-evaluation)
- [8. Profile-Based Personalization](#8-profile-based-personalization)
- [9. Blind Navigation System](#9-blind-navigation-system)
- [10. Implementation](#10-implementation)
- [11. Evaluation and Discussion](#11-evaluation-and-discussion)
- [12. Future Work](#12-future-work)
- [13. Conclusion](#13-conclusion)
- [14. Team Contributions](#14-team-contributions)
- [15. Acknowledgements](#15-acknowledgements)
- [16. References](#16-references)
- [17. Appendix](#17-appendix)

---

## 1. Introduction

### 1.1 Context

tpgFlex is the on-demand, shared minibus service operated by the Transports publics genevois (tpg) in the canton of Geneva. Unlike a fixed-line bus, it routes a vehicle to a passenger after a request and aggregates several passengers travelling in a similar direction. The service was introduced primarily to extend public transport into low-density peri-urban and rural zones of the canton where conventional scheduled lines are not economical. Booking is performed through a digital application, which makes the digital interface itself a gateway to mobility: a passenger who cannot use the application cannot, in practice, use the service.

### 1.2 The accessibility gap

The baseline tpgFlex application was designed around an able-bodied, digitally fluent passenger. For users with disabilities, several gaps remained. A blind passenger could complete a booking but received no assistance in locating the correct vehicle on arrival, which is the moment of greatest anxiety in an on-demand context where the vehicle is not at a fixed bay. A wheelchair user had no way to confirm in advance whether a stop offered level boarding, a lowered kerb, or sufficient room to manoeuvre, and no channel to request that the driver deploy the ramp. A deaf passenger depended on audio announcements with no mirrored visual confirmation. Elderly and low-digital-literacy users encountered a booking flow with small text and many choices. Across all of these groups, a single structural deficiency recurred: the system offered no mechanism for passengers to *report* an accessibility problem or to *benefit* from problems that other passengers had already reported.

### 1.3 Why Geneva

Geneva presents a combination of conditions that make this problem both acute and representative. The canton is multilingual, with French as the working language but a large international population; the urban core is dense, while the service area extends into rural communes where infrastructure such as tactile paving, lit shelters, and mobile coverage is inconsistent. The population is ageing, increasing the share of riders with reduced mobility or sensory impairment. The on-demand nature of tpgFlex amplifies the navigation problem, because there is no permanent infrastructure at many pickup points to orient a passenger.

### 1.4 Research question

Mirroring Problem Statement #4, the project addressed a single research question:

> How can the current tpgFlex application be improved to make it more accessible and inclusive for passengers with disabilities, including in the rural areas the service is intended to reach?

### 1.5 Scope

The project considered five user profiles in addition to the standard passenger: blind and low-vision users, wheelchair and mobility-impaired users, deaf and hard-of-hearing users, low-digital-literacy users, and elderly users. These profiles were chosen because they correspond to the disability categories most affected by public-transport barriers and because they were the populations served by the organizations consulted during user research.

### 1.6 Contributions

The contributions of this project are:

- A **blind navigation layer** that guides a passenger over the last metres to the vehicle using on-device computer vision, optical character recognition, compass heading, step counting, and spatial audio.
- A **two-tier crowdsourcing system** combining one-time human stop surveys with continuous passive sensing from passengers' phones, aggregated through a trust-weighted evidence model with temporal decay.
- An **Epicollect-based survey methodology** and a **rule-based evaluator** that converts field observations into five user-facing stop scores.
- A **profile-based personalization system** that adapts both the accessibility scoring and the user interface to each of six user types.
- A grounding of all of the above in **field research** with two organizations supporting people with disabilities in the Geneva area.

---

## 2. Background and Related Work

### 2.1 Public-transport accessibility tools

Several systems address aspects of accessible mobility. Wheelmap and the broader OpenStreetMap accessibility tagging effort allow contributors to mark the wheelchair-accessibility of points of interest, but their coverage is sparse and uneven, and the tags are static descriptions rather than live conditions. Microsoft Soundscape pioneered three-dimensional spatial audio for orientation of blind pedestrians, demonstrating the value of audio beacons, but it targeted general urban navigation rather than a specific transport service and was eventually discontinued. NaviLens uses high-density colour markers that a phone camera can read at distance to provide signage information to blind users, but it requires physical markers to be installed at every location, which does not scale to rural on-demand stops. These systems established important techniques — audio beacons, camera-read signage, crowdsourced tagging — but none closed the loop from passenger-contributed data back into the routing of a transport service.

### 2.2 Crowdsourced accessibility data

Crowdsourcing accessibility information is attractive because authoritative surveys are expensive and quickly become stale. In practice, two recurring failures limit purely crowdsourced approaches. First, coverage gaps: OpenStreetMap accessibility attributes are present for only a small fraction of relevant features, and the rural areas most in need of data are the least covered. Second, the active-contribution problem: systems that rely entirely on users actively reporting tend to collect data only where motivated contributors already are, and the data decays without anyone updating it. A complementary line of work uses passive sensing — inferring surface roughness or kerb impacts from a phone's inertial sensors during normal travel — which removes the contribution burden but raises questions of signal interpretation and privacy.

### 2.3 Voice-first interfaces and AI assistants

Voice assistants have become a primary interaction modality for blind and low-vision users and for users with limited literacy. Speech recognition and synthesis are now available natively in the browser, and large language models make it feasible to extract structured intent from free-form spoken requests. Voice-first design, however, is not simply text-to-speech bolted onto a visual interface; it requires the information architecture to be linear, confirmable, and forgiving of error, which has implications for the whole booking flow.

### 2.4 Trust modeling and Bayesian aggregation

When multiple contributors report on the same fact, their reports must be combined into a single belief, and not all contributors are equally reliable. The literature on crowdsourced labelling treats this as an evidence-aggregation problem in which each contributor has a latent reliability and the aggregate belief is updated in a Bayesian fashion as reports arrive. This project applied a deliberately simplified version of that idea — reputation-weighted evidence with temporal decay — appropriate to a course project rather than a full probabilistic graphical model.

### 2.5 The gap addressed

Most existing solutions treat disabled users as an edge case layered onto an able-bodied design, perform poorly in rural areas, depend entirely on active reporting, or stop at displaying information without feeding it back into routing decisions. The project described here addresses all four: accessibility is a first-class design axis through the profile system; rural realities are explicitly encoded in the survey items; passive sensing supplements active reports to mitigate the cold-start and decay problems; and the aggregated accessibility picture is fed back into route selection so that each contribution improves subsequent trips.

---

## 3. User Research and Stakeholder Engagement

### 3.1 Field visits

To ground the design in real requirements rather than assumptions, the team visited two organizations supporting people with disabilities in the Geneva area. The visits were conducted as semi-structured interviews with both support staff and end-users, supplemented by direct observation of how members currently plan and undertake journeys on public transport.

- **[Organization 1]** — [purpose of visit; date]. The visit focused on [blind and low-vision mobility / orientation training].
- **[Organization 2]** — [purpose of visit; date]. The visit focused on [wheelchair and mobility users / independent travel].

The interview protocol asked participants to walk through a recent journey, to identify the points at which they felt uncertain or unsafe, and to describe any workarounds they had developed. Staff were asked separately about the barriers they most frequently helped members overcome.

### 3.2 Key findings from interviews

The findings are grouped below by disability profile. They are representative observations distilled from the interviews and should be read as design inputs rather than statistically sampled results.

**Blind and low-vision users**
- Difficulty identifying the correct vehicle on arrival, which is acute for an on-demand service where the vehicle is not at a fixed bay.
- Heightened anxiety at transfer points and unfamiliar stops.
- Audio beacons, where present, were not always functioning, and there was no way to know in advance.

**Wheelchair and mobility users**
- Uncertainty about whether the ramp would be available and deployed.
- Blocked or absent kerb cuts and narrow approach paths, particularly in rural areas.
- No advance information about manoeuvring space at the stop.

**Deaf and hard-of-hearing users**
- Over-reliance on audio announcements, with no visual confirmation that the booked vehicle had arrived.

**Elderly and low-digital-literacy users**
- Small text and a booking flow with too many choices.
- A general fear of getting lost once away from familiar surroundings.

**Common theme across all groups**
- The system gave passengers no way to report problems they encountered, and no way to learn from problems other passengers had already encountered.

The visits also produced photographic documentation of the field context, used internally to align the team on the lived experience of the target users.

![Figure 10: Site visit photos](./figures/figure_10_site_visits.png)
*Figure 10 — Photographs from the team's field visits to the two partner organizations supporting people with disabilities in the Geneva area.*

### 3.3 Translation into design requirements

Each interview finding was mapped to a concrete feature in the project. The mapping below shows the traceability from observed need to implemented response.

| User need observed | Feature introduced |
|---|---|
| Cannot identify the correct vehicle on arrival | Camera-assisted last-metre guidance with OCR reading of the vehicle route number |
| Audio beacon dead or unreliable at the stop | One-tap crowdsource report type for a non-functioning audio beacon |
| Uncertainty about ramp availability and deployment | In-app ramp request pushed live to the driver panel, with driver acknowledgement |
| No advance knowledge of stop accessibility | Epicollect stop survey feeding per-profile accessibility scores |
| No visual confirmation of arrival (deaf users) | Visual-first interface mode mirroring audio cues as text and vibration |
| Complex flow and small text (elderly / low literacy) | Simplified interface mode with larger text and fewer choices |
| Different barriers matter to different users | Profile-based scoring so the same stop is evaluated per user type |
| No channel to report or learn from problems | Active crowdsource reporting plus passive sensing, fed back into routing |
| Anxiety once a delay occurs at pickup | Passenger readiness status ("Ready", "Walking", "Need more time", "Request assistance") with a driver wait-or-depart decision |

---

## 4. System Overview

The delivered system comprises five layers. The first existed in the baseline; the remaining four were designed and built during this project. The architecture and data flows are summarized in Figure 11, and the entry point to the application is shown in Figure 4.

**Voice booking core (baseline).** A passenger speaks or types a destination; the system extracts structured intent using a large language model with a keyword-parser fallback, confirms the details, and creates a booking. This core was present in the baseline and was retained.

**Blind navigation layer (added).** After booking, a blind passenger can enter a guided navigation mode that combines GPS, compass, step counting, and spatial audio for orientation, and an on-device camera pipeline for last-metre guidance and reading the vehicle route number.

**Crowdsource accessibility layer (added).** Passengers contribute accessibility evidence both actively, through one-tap reports, and passively, through derived events from their phones' inertial sensors during travel. Evidence is aggregated with trust weighting and temporal decay and is fed back into routing.

**Epicollect-based stop evaluation engine (added).** Field surveyors record structured observations at stops using an Epicollect form; a rule-based evaluator converts these observations into five user-facing scores per stop, weighted per profile.

**User profile personalization system (added).** A declared user profile selects both the scoring weights and the interface mode, so that the same stop and the same navigation page present differently to different users.

![Figure 11: System architecture diagram](./figures/figure_11_architecture.png)
*Figure 11 — High-level system architecture showing the five layers — voice booking, blind navigation, crowdsource sensing, Epicollect rule evaluator, and profile personalization — and the data flows that connect field surveys and passenger sensing to the user-facing scores and routing decisions.*

![Figure 4: Main application homepage](./figures/figure_4_homepage.png)
*Figure 4 — The tpgFlex main interface, the entry point from which passengers book a ride by voice or text and from which the navigation, evaluation, and profile features are reached.*

---

## 5. Epicollect Crowdsourced Survey Methodology

Structured field data collection was central to the project, and Epicollect5 was the instrument used to gather it.

### 5.1 What is Epicollect5

Epicollect5 is an open-source citizen-science data-collection platform developed at the Centre for Genomic Pathogen Surveillance and Imperial College London. It allows a researcher to define a custom form through a web interface, collect GPS-tagged entries through a mobile application or web client, and export the collected data as CSV or JSON. It is free for academic and non-commercial use. Epicollect5 was selected for this project because it removed the need to build and maintain a separate survey application, provided structured and exportable data out of the box, and supported the bilingual, checkbox-based form that the survey design required.

![Figure 1: Epicollect project setup](./figures/figure_1_epicollect_setup.png)
*Figure 1 — The Epicollect5 project configuration for the tpgFlex stop-observation campaign, showing the form structure and project settings used by surveyors.*

### 5.2 Survey design

The survey was designed as a single contribution form with a contribution-type selector that distinguished two kinds of submission: a place observation, recorded at a specific stop, and a ride evaluation, recorded for a trip rather than a stop. Place observations were captured as a multi-select checkbox question, *Observations du lieu / Place observations*, whose items span the **Accessibility** and **Safety** dimensions; ride evaluations were captured as a separate multi-select question, *Retour d'expérience / Experience Feedback — Quick Tags*, corresponding to the **Ride Experience** dimension. All items were presented bilingually in French and English so that surveyors could record in either language.

The items were chosen so that each maps to at least one disability profile or to the safety dimension, and each was motivated by a finding from the field research in Section 3. The accessibility items are grouped below by the profile to which they are most relevant; several items are relevant to more than one profile and are weighted accordingly in the evaluator (Section 7 and Appendix B).

**Accessibility — wheelchair and mobility items**

| French | English |
|---|---|
| Surface dure et stable | Hard stable surface |
| Bordure abaissée présente | Lowered kerb present |
| Embarquement de plain-pied avec le véhicule | Level boarding with vehicle |
| Espace suffisant pour manœuvrer un fauteuil | Sufficient wheelchair manoeuvring space |
| Pente du chemin | Path slope |
| Surface meuble ou irrégulière | Soft or uneven surface |
| Forte pente | Steep slope |
| Obstacles dans la zone d'attente | Obstacles in waiting area |

**Accessibility — blind, low-vision, deaf and low-digital-literacy items**

| French | English |
|---|---|
| Bandes podotactiles de guidage | Tactile guidance paving |
| Bandes podotactiles d'éveil au bord | Tactile warning strip at boarding edge |
| Signalétique à fort contraste visuel | High-contrast signage |
| Nom de l'arrêt clairement visible et lisible | Stop name clearly visible and readable |
| Information en braille | Braille info |
| Affichage temps réel (PID) | Passenger Information Display (PID) |
| Pictogrammes universels | Universal pictograms |
| Plan du réseau | Network Map |

**Safety and comfort items (with elderly relevance)**

| French | English |
|---|---|
| Éclairage suffisant | Adequate lighting |
| Passage piéton proche | Pedestrian crossing nearby |
| Commerce ou Hôpital-pharmacie proche | Nearby shop / hospital / pharmacy |
| Zone scolaire proche | School nearby |
| Zone sombre | Dark area |
| Zone isolée | Isolated area |
| Route à vitesse élevée (> 50 km/h) | High-speed road |
| Couverture mobile faible | Poor mobile signal |
| Abri disponible | Shelter available |
| Banc disponible | Bench available |
| Zone calme | Quiet area |
| Stationnement vélo proche | Bike parking nearby |

The rationale for each item traces back to the user research. Tactile guidance and warning paving, braille information, and high-contrast, clearly readable stop names respond directly to the blind users' difficulty in confirming they are at the right stop. Lowered kerbs, level boarding, and manoeuvring space respond to the wheelchair users' uncertainty about approach and boarding. Passenger Information Displays, universal pictograms, and network maps respond to the deaf and low-digital-literacy users' need for visual rather than audio information. Several items — poor mobile signal, soft or uneven surface, isolated area, high-speed road, absence of shelter — were included specifically because the tpgFlex service area extends into rural communes where these conditions are common and were repeatedly raised as barriers to independent travel.

![Figure 2: Epicollect survey form](./figures/figure_2_epicollect_form.png)
*Figure 2 — The StopObservation form as completed by surveyors in the field, showing the bilingual checkbox items for place observations and ride-experience quick tags.*

### 5.3 Data collection process

Surveyors visited selected tpgFlex stops across the canton of Geneva, including both dense urban stops and rural stops, and recorded one Epicollect entry per observation. To support the confidence weighting described in Section 7, the protocol sought a minimum of N independent observations per stop from different surveyors, so that a single surveyor's judgement would not dominate a stop's score. The form was refined iteratively: early field use revealed items that were ambiguous or rarely applicable, and the item set and wording were adjusted before the main collection effort.

### 5.4 Dataset structure

The exported dataset contains one row per submitted observation. The key columns are the stop name, GPS latitude and longitude, the contribution type, the place-observation multi-select value, the ride-experience multi-select value, and a timestamp. Each multi-select column contains the bilingual checkbox labels that the surveyor selected, stored as a list of `French / English` strings. The ingestion pipeline parses these values, retains the French side as the canonical label, and routes each item to its scoring block. The total number of observations collected over the campaign was [N] across [M] stops.

![Figure 3: Epicollect raw dataset CSV export](./figures/figure_3_epicollect_dataset.png)
*Figure 3 — A sample of the raw Epicollect CSV export, showing the per-stop observation columns and the bilingual checkbox labels recorded by surveyors.*

### 5.5 Why crowdsourcing the survey is academically interesting

Field data collection by multiple human surveyors is itself an instance of crowdsourcing: active, human-in-the-loop sensing in which contributors apply judgement to produce structured labels. The academic interest of the project lies in combining this with the passive sensing layer described in Section 6 to form a two-tier crowdsourcing system. Humans tag each stop once, producing a structured baseline; passengers' phones then continuously refine that picture during ordinary travel, detecting changes that a one-time survey cannot capture. This dual-layer arrangement — a sparse, high-quality human baseline continuously updated by dense, lower-quality passive observations — is the project's principal novelty.

---

## 6. Crowdsource and AI Layer

### 6.1 Passive sensing using mobile sensors

The passive layer derives accessibility-relevant events from the inertial and location sensors that a passenger's phone already exposes during a normal trip. The accelerometer is used to detect surface roughness, kerb impacts, and sudden jolts; the gyroscope is used to detect ramps, sharp turns, and the pitch jolt characteristic of a kerb. The GPS provides location, and the resulting speed profile reveals delays and detours. Processing is profile-aware, because the inertial signature of a motor wheelchair differs from that of a manual wheelchair, which differs again from walking; the same raw motion is therefore interpreted differently depending on the declared profile. A data-minimization principle governs the layer: only derived events — for example, "rough surface detected at this location" — leave the device, while the raw sensor traces never do.

### 6.2 Active crowdsource reports

Alongside passive sensing, passengers can file explicit reports through one-tap categories: blocked kerb, vehicle issue, broken ramp, no shelter, dead audio beacon, missing tactile paving, and construction. For blind users the reporting flow is voice-driven so that it does not depend on locating a visual control. Each report is stored with its type, location, an initial confidence, and an expiry derived from the temporal-decay configuration described below.

### 6.3 Trust-weighted aggregation model

Reports about the same location and type must be combined into a single belief, and contributors are not equally reliable. Each report carries a confidence score initialized from the reporter's reputation. A reporter's reputation grows when their reports are subsequently confirmed by others and decays when they are contradicted. As a consequence, a single report from a long-trusted contributor moves the aggregate belief more than many simultaneous reports from newly created accounts. This is a deliberately simplified, reputation-weighted form of Bayesian evidence aggregation, appropriate to the scope of a course project. The same mechanism provides a measure of resistance to Sybil and coordinated-manipulation attacks: because influence is gated by accumulated reputation and because agreement is counted per distinct user rather than per report, creating many fresh accounts to manufacture consensus is ineffective.

### 6.4 Temporal decay

Accessibility conditions are not permanent, and a report's influence should fade at a rate matching the physical reality it describes. Each report type is therefore assigned a half-life. The confidence of a report decays continuously according to

```
decayed_confidence = base_confidence × 0.5 ^ (hours_elapsed / half_life)
```

and a report whose decayed confidence falls below a threshold of 0.15 becomes inactive automatically and ceases to influence routing. A temporary obstruction such as a blocked kerb is assigned a short half-life of about two hours; a broken ramp, which may take days to repair, is assigned about three days; a structural absence such as missing tactile paving is treated as effectively permanent. The full configuration is given in Appendix C.

### 6.5 Routing feedback loop

The accessibility map is not a passive display but an input to routing. When a user requests a route, each candidate path is assigned a profile-aware risk score derived from the active and passive evidence near it, weighted by current confidence. Paths that pass close to high-confidence negative reports relevant to the user's profile are penalized and, where alternatives exist, avoided. This closes the loop between contribution and benefit: every report and every passively sensed event measurably changes the risk surface used to plan the next passenger's trip, so that the act of travelling improves the system for subsequent travellers.

---

## 7. Rule-Based Stop Evaluation

### 7.1 From Epicollect observations to user-facing scores

The evaluator converts field observations into five user-facing outputs per stop: **Accessibility**, **Safety**, **Punctuality**, **Ride Experience**, and **Service Regularity**. Three of these are derived from crowdsourced survey data: Accessibility and Safety from the place-observation form, and Ride Experience from the separate ride-evaluation form. The remaining two, Punctuality and Service Regularity, are properties of the operational service rather than of a stop's physical fabric and are intended to be derived from real-time GPS and schedule data; in the current implementation they are presented as operational indicators pending integration with live tpgFlex feeds (Section 11.2).

A design consequence of the survey structure is that Ride Experience is a network-wide score. Because a ride evaluation describes a trip rather than a stop and is submitted without a stop reference, all ride-experience feedback is aggregated into a single service-level score that is then shown identically on every stop, while Accessibility and Safety remain specific to each stop.

### 7.2 Scoring methodology

Each checkbox item carries a weight that is positive when the item improves the experience and negative when it degrades it. Weights are profile-specific: a blind user weights tactile paving heavily, whereas a wheelchair user weights lowered kerbs and level boarding heavily. For a given stop and profile, the raw score is the sum of the weights of the items observed at that stop that appear in that profile's weight table:

```
raw_score = Σ weight(item)  for each matched item
```

The raw score is then normalized against the range achievable by that weight table,

```
normalized = (raw_score − min_possible) / (max_possible − min_possible)
```

and discretized into three bands: **Good** for a normalized score of at least 0.70, **Fair** for at least 0.40, and **Poor** below 0.40. The bands are presented to the user with a colour code — green, orange, and red respectively.

### 7.3 Per-profile personalization

The user's declared profile selects which weight table is applied, so that the same stop produces a different score for a wheelchair user than for a blind user. As a worked example, a surveyed stop with level boarding, a lowered kerb, and ample manoeuvring space but no tactile paving and no audio information scores Good for a wheelchair user and Poor for a blind user from a single set of observations. To make the result transparent rather than opaque, a "Show details" expander reveals which observed items contributed positively and which contributed negatively to the displayed score. A confidence indicator, derived from the number of independent surveys recorded at the stop, communicates how much trust to place in the score.

![Figure 7: Stop evaluator UI](./figures/figure_7_stop_evaluator.png)
*Figure 7 — The stop evaluator interface, showing the five user-facing scores for a selected stop and the profile selector that re-evaluates the stop for a different user type.*

---

## 8. Profile-Based Personalization

### 8.1 Profile system

The personalization system defines six predefined profiles: standard, wheelchair, blind, deaf, low digital literacy, and elderly. Each profile carries two settings: a scoring profile, which determines the weight table used by the evaluator, and a user-interface mode, which determines how information is presented — voice-first, visual-first, simplified, or default. A profile is selected on first use and can be changed at any time.

### 8.2 Adaptive user interface

The interface mode adapts the presentation to the sensory and cognitive needs of the profile. In the **voice-first** mode used for blind users, controls are enlarged, audio and haptic feedback become the primary channel, and decorative visuals are suppressed. In the **visual-first** mode used for deaf users, every audio cue is mirrored as on-screen text and vibration so that no information is conveyed by sound alone. In the **simplified** mode used for elderly and low-digital-literacy users, text is enlarged, the number of choices on each screen is reduced, and synthesized speech is slowed. The profile is stored once on the backend and read by the frontend through a single profile-manager module, so that the interface mode is consistent across every page of the application rather than configured separately in each.

![Figure 8: Profile setup wizard](./figures/figure_8_profile_setup.png)
*Figure 8 — The onboarding wizard through which a user selects an accessibility profile and preferences, which then govern both scoring and interface behaviour across the application.*

### 8.3 Cross-feature personalization

The declared profile is a single setting with effects across the whole system. It selects the stop-scoring weight table, the route preferences and acceptable walking distance, the navigation interface, the synthesized-speech speed, and the feedback modalities used to confirm actions. The personalization is demonstrable as two concrete transformations: the same stop yields different scores under different profiles, and the same navigation page renders as a different interface under different profiles.

---

## 9. Blind Navigation System

### 9.1 Multi-sensor navigation stack

The navigation layer orients a blind passenger using the phone's own sensors. GPS provides absolute position, the compass provides heading, and a step counter derived from the accelerometer provides distance travelled. Instructions are expressed in steps rather than metres — for example, "turn right in 20 steps" — because step counts are more meaningful and more robust for a pedestrian than metric distances. Direction toward the destination is reinforced by a spatial audio beacon, implemented with the Web Audio API's stereo panning, so that the target is perceived as lying to the left or right of the current heading.

### 9.2 Camera-assisted last-metre guidance

The most difficult moment for a blind passenger — confirming and reaching the correct vehicle — is addressed by an on-device camera pipeline. Object detection runs in the browser using TensorFlow.js with the COCO-SSD model to identify obstacles in the path, and optical character recognition runs with Tesseract.js to read vehicle route numbers and signage. Guidance is delivered through stereo audio and haptic vibration patterns that encode direction and proximity. Privacy is preserved by performing all recognition on the device; camera frames are not uploaded, with the sole exception of a compressed copy streamed to an audience display during demonstrations.

### 9.3 Demo configuration

For demonstration, the full navigation runs on a phone while a laptop shows a live mirrored view for an audience. The two clients are linked by a WebSocket relay through the existing FastAPI backend, which forwards the phone's camera frame, map position, and current instruction to the display without storing them.

![Figure 5: Blind navigation phone UI](./figures/figure_5_navigate_user.png)
*Figure 5 — The phone interface used by the blind passenger during guided navigation, combining spatial-audio orientation with camera-based last-metre guidance.*

![Figure 6: Audience display screen](./figures/figure_6_navigate_display.png)
*Figure 6 — The laptop audience display, showing the live camera feed, the passenger's position on the map, and the current navigation instruction as subtitles.*

---

## 10. Implementation

The implementation favoured free, local-first technologies with no build step and no paid external services, so that the system could be deployed immediately and run at zero marginal cost. The principal technology choices and their justifications are summarized below.

| Component | Technology | Justification |
|---|---|---|
| Backend | FastAPI with SQLite, asyncio | Lightweight, asynchronous, suitable for WebSocket relays and background decay tasks without an external database |
| Frontend | Vanilla HTML and JavaScript, CDN-loaded libraries | No build step, easy to host and audit, fast to iterate |
| Maps | Leaflet with OpenStreetMap tiles | Free and key-less mapping |
| Routing | OSRM public demo server | Free pedestrian routing without an API key |
| In-browser ML | TensorFlow.js with COCO-SSD; Tesseract.js | On-device object detection and OCR, preserving privacy |
| Voice | Web SpeechSynthesis and SpeechRecognition APIs | Native speech without third-party services |
| Survey | Epicollect5 | Free citizen-science data collection and export |

All sensing and recognition are performed locally by default, and no component depends on a paid third-party service. The reasoning behind these choices was consistent: zero cost, immediate deployability, and privacy preservation by default. The complete source is available in the project's [GitHub Repository]([GITHUB_REPO_LINK]).

![Figure 9: Crowdsource accessibility map](./figures/figure_9_crowdsource_map.png)
*Figure 9 — The live accessibility map of Geneva, on which crowdsourced reports are colour-coded by type and sized by current confidence, so that high-confidence barriers are visually prominent.*

---

## 11. Evaluation and Discussion

### 11.1 What worked

Several elements of the design performed as intended in demonstration conditions. Profile-based scoring produced visibly different evaluations of the same stop across user types, validating the central premise that accessibility is profile-dependent. Camera-based optical character recognition read vehicle route numbers reliably under the lighting and distance conditions of the demonstration. Step-based navigation with compass verification proved more reliable than metre-based navigation for the indoor demonstration, where GPS alone was insufficient. Epicollect proved usable by surveyors with no technical background, which is a precondition for any real field campaign.

### 11.2 Limitations

The work has clear limitations. GPS accuracy in urban canyons is the fundamental constraint on last-metre navigation precision and cannot be fully overcome by the current sensor fusion. The crowdsourcing layer requires a critical mass of contributors to be useful, and the cold-start condition was simulated with seeded data rather than evaluated with real traffic. The object-detection model, COCO-SSD, is trained on general imagery and does not recognize transport-specific features such as kerbs or tactile paving, limiting the richness of obstacle detection. Survey coverage was bounded by the number of surveyors the team could deploy within the project period. Finally, the Punctuality and Service Regularity scores are currently presented as operational indicators pending integration with live tpgFlex data and should be regarded as placeholders for that integration.

### 11.3 Ethical considerations

Because disability information is sensitive, the profile is stored client-side by default, and only the minimum necessary information is disclosed to drivers — for example, that a ramp is requested, not a passenger's full profile. Crowdsource reports are anonymous and are recorded at the level of locations and types rather than identifiable journeys, so that they cannot be reverse-engineered into an individual's travel history. Camera processing for navigation is performed entirely on-device, and frames are not uploaded except for the compressed demonstration mirror, which is disclosed to the user.

### 11.4 Generalizability

The architecture is not specific to Geneva. The same five-layer approach applies to any on-demand transport system, and only the survey item set and weight tables would need localization. Rural applicability was a primary design driver rather than an afterthought: the survey items explicitly encode rural conditions such as poor mobile coverage, unpaved surfaces, isolated locations, and high-speed adjacent roads, so the method is expected to transfer to other peri-urban and rural transport contexts.

---

## 12. Future Work

Several directions would extend the project beyond its current state. Integration with the live tpgFlex backend would replace the stubbed Punctuality and Service Regularity indicators with measured values. Federated learning for the passive-trace models would allow the shared interpretation model to improve while disability-related sensor data remained on each user's device. Indoor station navigation could be added using the GTFS-Pathways standard together with visual positioning, addressing the GPS-denied environments that currently limit precision. A caregiver companion application would let family members follow a journey live, addressing the anxiety reported by elderly users and their relatives. A driver-side reporting interface is a natural addition, since drivers observe more accessibility failures than any other actor. Multilingual expansion beyond French and English would broaden reach in Geneva's international population. Finally, a field deployment study with actual disabled riders over a multi-week period would move the evaluation from demonstration conditions to real use.

---

## 13. Conclusion

This project addressed Problem Statement #4 — how the current tpgFlex application can be made more accessible and inclusive — by treating accessibility as a first-class design axis rather than an accommodation layered onto an able-bodied product. The answer developed here is that an on-demand transport application can be made inclusive by personalizing both information and interface to each user's needs, by giving passengers a way to contribute and benefit from accessibility knowledge, and by guiding the most difficult moments of a journey with on-device sensing.

The work rests on four pillars. A blind navigation layer guides passengers over the last metres using camera, OCR, compass, step counting, and spatial audio. A two-tier crowdsourcing layer combines one-time human stop surveys with continuous passive sensing, aggregated through a trust-weighted, temporally decaying evidence model and fed back into routing. An Epicollect-based survey feeds a rule evaluator that produces five per-profile stop scores. A profile personalization system adapts scoring and interface across the whole application.

Taken together, the project demonstrated that disabled riders can improve the transport system simply by using it — each trip contributing evidence that benefits the next traveller — and that a free, local-first technology stack is sufficient to deliver real accessibility today, without proprietary services or recurring cost.

---

## 14. Team Contributions

| Team Member | Primary Responsibilities |
|---|---|
| [Team Member 1] | [Backend, FastAPI routes, database schema, OSRM integration] |
| [Team Member 2] | [Frontend UI, navigation interface, profile system] |
| [Team Member 3] | [Epicollect survey design, field data collection, rule evaluator] |
| [Team Member 4] | [Crowdsource AI layer, trust modeling, temporal decay, evaluation] |

All team members participated in user research, design discussions, the field visits to partner organizations, and report writing. The breakdown above reflects primary technical ownership of each component.

---

## 15. Acknowledgements

The team thanks Professor François Grey for his guidance throughout the Crowdsourcing and AI course, and Teaching Assistant Saray Quirant Perez for ongoing feedback on the project. We are grateful to the two partner organizations supporting people with disabilities in the Geneva area for hosting our field visits and sharing their members' experiences. We also thank the Epicollect5 team at Imperial College London for providing a free citizen-science platform, and the OpenStreetMap, OSRM, TensorFlow.js, and Tesseract.js communities for the open tooling on which this project depends.

---

## 16. References

[1] Aanensen, D. M., Huntley, D. M., Feil, E. J., al-Own, F., & Spratt, B. G. (2014). *EpiCollect: Linking smartphones to web applications for epidemiology, ecology and community data collection.* PLoS ONE. (Epicollect5 platform.)

[2] [Reference to be added — Microsoft Soundscape documentation and design overview.]

[3] OpenStreetMap Wiki. *Key:wheelchair and accessibility tagging guidelines.* (Accessed [date].)

[4] [Reference to be added — Bayesian aggregation and worker-reliability modeling in crowdsourced labelling, foundational paper.]

[5] World Wide Web Consortium (W3C). *Web Content Accessibility Guidelines (WCAG) 2.1.* W3C Recommendation, 2018.

[6] [Reference to be added — General Transit Feed Specification (GTFS) Pathways specification for in-station navigation.]

[7] Transports publics genevois (tpg). *tpgFlex on-demand service — official documentation.* (Accessed [date].)

[8] [Reference to be added — Crowdsourcing and AI course materials and lecture notes, François Grey.]

[9] [Reference to be added — NaviLens accessible-signage system technical overview.]

[10] [Reference to be added — Passive inertial sensing for surface and accessibility inference, representative paper.]

---

## 17. Appendix

### Appendix A — Full list of Epicollect survey items

The complete item set is listed below, grouped by scoring block and given bilingually. Accessibility and Safety items belong to the place-observation form; Ride Experience items belong to the separate ride-evaluation form.

**A.1 Accessibility block (place observations)**

| French | English |
|---|---|
| Surface dure et stable | Hard stable surface |
| Pente du chemin | Path slope |
| Bordure abaissée présente | Lowered kerb present |
| Embarquement de plain-pied avec le véhicule | Level boarding with vehicle |
| Espace suffisant pour manœuvrer un fauteuil | Sufficient wheelchair manoeuvring space |
| Surface meuble ou irrégulière | Soft or uneven surface |
| Forte pente | Steep slope |
| Obstacles dans la zone d'attente | Obstacles in waiting area |
| Bandes podotactiles de guidage | Tactile guidance paving |
| Bandes podotactiles d'éveil au bord | Tactile warning strip at boarding edge |
| Signalétique à fort contraste visuel | High-contrast signage |
| Nom de l'arrêt clairement visible et lisible | Stop name clearly visible and readable |
| Information en braille | Braille info |
| Affichage temps réel (PID) | Passenger Information Display (PID) |
| Pictogrammes universels | Universal pictograms |
| Plan du réseau | Network Map |

**A.2 Safety block (place observations)**

| French | English |
|---|---|
| Éclairage suffisant | Adequate lighting |
| Passage piéton proche | Pedestrian crossing nearby |
| Commerce ou Hôpital-pharmacie proche | Nearby shop / hospital / pharmacy |
| Zone scolaire proche | School nearby |
| Zone sombre | Dark area |
| Zone isolée | Isolated area |
| Route à vitesse élevée (> 50 km/h) | High-speed road |
| Couverture mobile faible | Poor mobile signal |
| Abri disponible | Shelter available |
| Banc disponible | Bench available |
| Zone calme | Quiet area |
| Stationnement vélo proche | Bike parking nearby |

**A.3 Ride Experience block (ride evaluation — Quick Tags)**

| French | English |
|---|---|
| Confortable | Comfortable |
| Serviable | Helpful |
| Accessible | Accessible |
| Montée facile | Easy boarding |
| Bon éclairage | Good lighting (inside vehicle) |
| Ponctuel | On time |
| Attente longue | Long waiting time |
| Accès difficile | Difficult access |
| Bonne expérience | Good experience |
| Rampe utilisée si nécessaire | Ramp deployed when needed |
| Annonces sonores fonctionnelles | Audio announcements working |
| Espace fauteuil disponible | Wheelchair space available |
| Véhicule propre | Clean vehicle |
| Je me suis senti en sécurité | Felt safe during ride |
| Trajet cahoteux | Bumpy ride |
| Porte coincée | Door stuck |
| Arrêts annoncés clairement | Stops clearly announced |
| Information visuelle claire | Clear visual information |
| Trajet facile à comprendre | Easy to understand ride |
| Véhicule surchargé | Overcrowded vehicle |

### Appendix B — Scoring weight tables

The weight tables used by the evaluator are given below, one per accessibility profile, followed by the safety and ride-experience tables. A positive weight indicates that the presence of the item improves the score for that profile; a negative weight indicates a barrier. An item may appear in several tables with different weights.

**B.1 Wheelchair / mobility profile**

| Item | Weight |
|---|---|
| Embarquement de plain-pied avec le véhicule | +4 |
| Surface dure et stable | +3 |
| Bordure abaissée présente | +3 |
| Espace suffisant pour manœuvrer un fauteuil | +3 |
| Abri disponible | +1 |
| Pente du chemin | −1 |
| Obstacles dans la zone d'attente | −2 |
| Surface meuble ou irrégulière | −3 |
| Forte pente | −4 |

**B.2 Blind / low-vision profile**

| Item | Weight |
|---|---|
| Bandes podotactiles de guidage | +4 |
| Bandes podotactiles d'éveil au bord | +4 |
| Signalétique à fort contraste visuel | +2 |
| Nom de l'arrêt clairement visible et lisible | +2 |
| Information en braille | +2 |
| Affichage temps réel (PID) | +1 |
| Zone calme | +1 |
| Obstacles dans la zone d'attente | −2 |
| Route à vitesse élevée (> 50 km/h) | −3 |

**B.3 Deaf / hard-of-hearing profile**

| Item | Weight |
|---|---|
| Affichage temps réel (PID) | +4 |
| Nom de l'arrêt clairement visible et lisible | +3 |
| Pictogrammes universels | +3 |
| Plan du réseau | +2 |
| Signalétique à fort contraste visuel | +2 |

**B.4 Low-digital-literacy profile**

| Item | Weight |
|---|---|
| Affichage temps réel (PID) | +3 |
| Pictogrammes universels | +3 |
| Plan du réseau | +3 |
| Nom de l'arrêt clairement visible et lisible | +2 |
| Signalétique à fort contraste visuel | +2 |

**B.5 Elderly profile**

| Item | Weight |
|---|---|
| Banc disponible | +3 |
| Abri disponible | +2 |
| Éclairage suffisant | +2 |
| Surface dure et stable | +2 |
| Pente du chemin | −1 |
| Surface meuble ou irrégulière | −2 |
| Forte pente | −3 |
| Obstacles dans la zone d'attente | −2 |

**B.6 Safety table**

| Item | Weight |
|---|---|
| Éclairage suffisant | +3 |
| Passage piéton proche | +2 |
| Commerce ou Hôpital-pharmacie proche | +2 |
| Zone scolaire proche | +1 |
| Couverture mobile faible | −2 |
| Zone sombre | −3 |
| Zone isolée | −3 |
| Route à vitesse élevée (> 50 km/h) | −3 |

**B.7 Ride-experience table (network-wide)**

| Item | Weight |
|---|---|
| Bonne expérience | +3 |
| Je me suis senti en sécurité | +3 |
| Confortable | +2 |
| Serviable | +2 |
| Accessible | +2 |
| Montée facile | +2 |
| Ponctuel | +2 |
| Rampe utilisée si nécessaire | +2 |
| Annonces sonores fonctionnelles | +2 |
| Espace fauteuil disponible | +2 |
| Véhicule propre | +2 |
| Arrêts annoncés clairement | +2 |
| Information visuelle claire | +2 |
| Trajet facile à comprendre | +2 |
| Bon éclairage | +1 |
| Attente longue | −2 |
| Trajet cahoteux | −2 |
| Véhicule surchargé | −2 |
| Accès difficile | −3 |
| Porte coincée | −3 |

### Appendix C — Report type half-life table

The temporal-decay configuration assigns each crowdsource report type a half-life chosen to match the persistence of the condition it describes. The values below are design parameters; a report becomes inactive once its decayed confidence falls below 0.15.

| Report type | Half-life | Rationale |
|---|---|---|
| Blocked kerb | 2 hours | Typically a transient obstruction (parked vehicle, bins) |
| Vehicle issue | 6 hours | Tied to a specific vehicle in service, not the location |
| Dead audio beacon | 7 days | Awaits a maintenance visit |
| Construction | 14 days | Persists for the duration of works |
| Broken ramp | 3 days | Awaits repair, but may be fixed within days |
| No shelter | 30 days | A semi-permanent infrastructure gap |
| Missing tactile paving | Permanent | A structural absence that does not self-resolve |

### Appendix D — Repository structure

The principal folders and files of the repository, excluding generated artefacts, are shown below.

```
AI.BILITY-tpgFlex/
├── backend/
│   ├── main.py                 FastAPI app: REST + WebSocket routes
│   ├── database.py             SQLite connection
│   ├── stop_evaluator.py       Rule-based per-profile scoring engine
│   ├── epicollect_sync.py      Live Epicollect API sync into observations
│   ├── import_epicollect.py    Offline CSV importer for survey exports
│   ├── user_profile.py         Profile storage and preferences
│   ├── seeBooking.py           Booking inspection utility
│   ├── agent/
│   │   ├── intent.py           LLM intent detection with keyword fallback
│   │   └── booking_engine.py   Stop matching, vehicle assignment, booking
│   └── mock_data/
│       ├── seed.py             Database seeding
│       └── seed_observations.py  Demo stop observations
├── frontend/
│   ├── index.html              Passenger booking UI
│   ├── driver_panel.html       Driver alerts, ramp + readiness panel
│   ├── navigate_user.html      Blind navigation phone interface
│   ├── navigate_display.html   Audience mirror display
│   ├── navigate_map.html       Map component for navigation
│   ├── stop_evaluator.html     Stop evaluation map and scores
│   ├── profile_setup.html      Onboarding wizard
│   ├── profile_settings.html   Profile management
│   ├── profile_manager.js      Single source of truth for the active profile
│   └── profile_styles.css      Shared profile-mode styling
├── requirements.txt
├── setup.sh
└── README.md
```
