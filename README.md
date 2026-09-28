\# EDResolve



\### Experiential Decision Support for Emergency Department Operations



EDResolve is an experiential decision-support system for recurring Emergency Department operational bottlenecks.



The central premise is:



> \*\*When the same operational problem happens again, the system should not have to reason from zero.\*\*



EDResolve combines \*\*experiential memory, operational state modeling, constraint validation, counterfactual simulation, and outcome learning\*\* to transform previous operational episodes into reusable decision knowledge.



Instead of remembering only \*what happened\*, EDResolve captures:



\- the operational conditions surrounding the problem

\- the bottleneck and its dependencies

\- the interventions considered

\- the constraints affecting those interventions

\- the expected consequences

\- the action selected

\- the observed outcome

\- the prediction error

\- the resulting lesson



This creates a closed experiential learning loop:



```mermaid

flowchart LR

&#x20;   A\["Operational State"] --> B\["Experience Retrieval"]

&#x20;   B --> C\["Reasoning"]

&#x20;   C --> D\["Counterfactual Evaluation"]

&#x20;   D --> E\["Decision"]

&#x20;   E --> F\["Outcome"]

&#x20;   F --> G\["Learning"]

&#x20;   G --> B

```



\---



\# Why EDResolve?



Emergency Department delays can emerge from interacting operational dependencies rather than a single isolated event.



A transfer may depend simultaneously on:



```text

ED capacity

&#x20;     +

destination-unit capacity

&#x20;     +

bed readiness

&#x20;     +

transport availability

&#x20;     +

interdepartmental coordination

```



A system that only analyzes the current state can determine what appears feasible now.



EDResolve additionally asks:



> \*\*What happened the last time we faced a similar operational deadlock?\*\*



Historical experience is treated as contextual evidence rather than a command to repeat a previous decision.



\---



\# Core Architecture



```mermaid

flowchart TD



&#x20;   A\["Current ED Operational State"] --> B\["World Model"]



&#x20;   B --> C\["Bottleneck Fingerprint"]



&#x20;   C --> D\["Hindsight Recall"]



&#x20;   D --> E\["Historical Experiences"]



&#x20;   B --> F\["GPT-OSS Candidate Generation"]

&#x20;   E --> F



&#x20;   F --> G\["Candidate Interventions"]



&#x20;   G --> H\["Hard Constraint Validation"]



&#x20;   H -->|Feasible| I\["Counterfactual Simulation"]

&#x20;   H -->|Infeasible| X\["Reject"]



&#x20;   I --> J\["Risk-Aware Selection"]



&#x20;   J --> K\["Operational Action"]



&#x20;   K --> L\["Observed Outcome"]



&#x20;   L --> M\["Expected vs Actual"]



&#x20;   M --> N\["Learning Signal"]



&#x20;   N --> O\["Hindsight Retain"]



&#x20;   O --> D

```



The architecture deliberately separates:



\*\*memory → reasoning → feasibility → simulation → selection → learning\*\*



rather than allowing the language model to directly determine the final action.



\---



\# Resolution Memory



\## From memory of facts to memory of decisions



A conventional memory system may retain:



```text

"Expedite bed cleaning."

```



EDResolve instead aims to retain the decision context:



```mermaid

flowchart TD



&#x20;   A\["Operational Context"] --> B\["Bottleneck"]



&#x20;   B --> C\["Available Actions"]



&#x20;   C --> D\["Constraints"]



&#x20;   D --> E\["Counterfactual Outcomes"]



&#x20;   E --> F\["Selected Action"]



&#x20;   F --> G\["Actual Outcome"]



&#x20;   G --> H\["Prediction Error"]



&#x20;   H --> I\["Lesson"]



&#x20;   I --> J\["Reusable Experience"]

```



A future episode can therefore retrieve not just a previous action, but the circumstances in which that action worked or failed.



\---



\# Counterfactual Experience Reuse



Historical experience is not blindly replayed.



The current operational state may differ significantly from the historical case.



Therefore EDResolve uses historical experience to \*\*generate and contextualize candidates\*\*, then evaluates those candidates under the current state.



```mermaid

flowchart TD



&#x20;   A\["Historical Experience"] --> C\["Context Matching"]



&#x20;   B\["Current Operational State"] --> C



&#x20;   C --> D\["Candidate Intervention"]



&#x20;   D --> E\["Hard Constraint Check"]



&#x20;   E -->|Feasible| F\["Counterfactual Simulation"]



&#x20;   E -->|Infeasible| G\["Rejected"]



&#x20;   F --> H\["Simulated Outcomes"]



&#x20;   H --> I\["Risk / Utility Analysis"]



&#x20;   I --> J\["Selected Intervention"]

```



This creates an important distinction:



> A previous success becomes evidence for a new decision, not a hard-coded rule.



\---



\# Decision Pipeline



```mermaid

flowchart TD



&#x20;   A\["Current State"] --> B\["Structured World Model"]



&#x20;   B --> C\["Operational Dependency Graph"]



&#x20;   C --> D\["Bottleneck Fingerprint"]



&#x20;   D --> E\["Hindsight Query"]



&#x20;   E --> F\["Relevant Experiences"]



&#x20;   F --> G\["GPT-OSS"]



&#x20;   B --> G



&#x20;   G --> H\["Candidate Interventions"]



&#x20;   H --> I\["OR-Tools Constraint Layer"]



&#x20;   I --> J\["SimPy Counterfactual Evaluation"]



&#x20;   J --> K\["Deterministic Risk-Aware Selection"]



&#x20;   K --> L\["Operational Decision"]



&#x20;   L --> M\["Outcome"]



&#x20;   M --> N\["Prediction Error"]



&#x20;   N --> O\["Experience Construction"]



&#x20;   O --> P\["Hindsight Retain"]



&#x20;   P --> E

```



\---



\# Separation of Responsibilities



Each subsystem has a deliberately constrained responsibility.



| Component | Responsibility |

|---|---|

| \*\*Hindsight\*\* | Long-term experiential memory |

| \*\*GPT-OSS\*\* | Candidate generation and reasoning |

| \*\*LangGraph\*\* | Stateful agent orchestration |

| \*\*NetworkX\*\* | Operational dependency graph |

| \*\*PM4Py\*\* | Process and workflow analysis |

| \*\*XGBoost\*\* | Conventional bottleneck prediction baseline |

| \*\*OR-Tools\*\* | Hard operational constraints |

| \*\*SimPy\*\* | Counterfactual discrete-event simulation |

| \*\*PostgreSQL\*\* | Structured state and audit persistence |

| \*\*FastAPI\*\* | Backend service layer |

| \*\*React / TypeScript\*\* | Decision-support interface |



\---



\# Decision Authority



The language model does not directly control the final decision path.



```mermaid

flowchart LR



&#x20;   A\["GPT-OSS"] --> B\["Candidate Actions"]



&#x20;   B --> C\["Constraint Validation"]



&#x20;   C -->|Infeasible| D\["Reject"]



&#x20;   C -->|Feasible| E\["SimPy"]



&#x20;   E --> F\["Counterfactual Outcomes"]



&#x20;   F --> G\["Deterministic Selection"]



&#x20;   G --> H\["Selected Action"]

```



The intended authority structure is:



```text

LLM

&#x20;↓

Propose



Constraint Layer

&#x20;↓

Filter



Simulator

&#x20;↓

Evaluate



Decision Engine

&#x20;↓

Select

```



This makes the final decision path more deterministic and auditable.



\---



\# Operational State Model



The prototype represents operational state using structured variables such as:



```text

Patients in ED

Boarding patients

Pending transfers

Unresolved transfers



ICU capacity

HDU capacity

Beds waiting for cleaning



Transport teams

Transport queue



Bed manager availability

Senior coordinator availability

```



The state is transformed into a structured world model and a bottleneck fingerprint.



Example:



```text

Bottleneck:

&#x20;   ICU\_BED\_CLEANING



Capacity pressure:

&#x20;   0.90



Transport pressure:

&#x20;   0.20



Coordination pressure:

&#x20;   0.00



Process delay:

&#x20;   0.73



Resource conflict:

&#x20;   0.80



Dominant dependency:

&#x20;   BED\_CLEANING

```



These values are synthetic operational-model features used by the prototype.



\---



\# Bottleneck Fingerprint



```mermaid

flowchart LR



&#x20;   A\["Raw Operational State"] --> B\["Capacity Pressure"]



&#x20;   A --> C\["Transport Pressure"]



&#x20;   A --> D\["Coordination Pressure"]



&#x20;   A --> E\["Process Delay"]



&#x20;   A --> F\["Resource Conflict"]



&#x20;   B --> G\["Bottleneck Fingerprint"]

&#x20;   C --> G

&#x20;   D --> G

&#x20;   E --> G

&#x20;   F --> G



&#x20;   G --> H\["Dominant Dependency"]

```



The fingerprint gives the memory and reasoning layers a normalized representation of the operational situation.



\---



\# Current Intervention Space



The prototype currently supports a bounded operational action space:



```text

WAIT

EXPEDITE\_BED\_CLEANING

REQUEST\_ALTERNATIVE\_UNIT

PRIORITIZE\_TRANSPORT

ESCALATE\_TO\_BED\_MANAGER

```



Constraining the action space improves:



\- interpretability

\- counterfactual reproducibility

\- evaluation

\- auditability



The same architecture can later support a larger intervention space.



\---



\# Counterfactual Simulation



EDResolve uses a discrete-event operational simulator to compare feasible interventions.



```mermaid

flowchart TD



&#x20;   A\["Current State"] --> B\["Candidate Action"]



&#x20;   B --> C\["SimPy Event Model"]



&#x20;   C --> D\["Resources"]



&#x20;   C --> E\["Queues"]



&#x20;   C --> F\["Transfer Events"]



&#x20;   D --> G\["State Evolution"]

&#x20;   E --> G

&#x20;   F --> G



&#x20;   G --> H\["Resolution Outcome"]



&#x20;   H --> I\["Operational Metrics"]



&#x20;   I --> J\["Decision Engine"]

```



The simulator currently evaluates signals such as:



\- resolution status

\- resolution time

\- boarding time

\- escalation count

\- resource conflicts

\- utility score



The synthetic simulator is an \*\*algorithm-development environment\*\* and is not evidence of real-world hospital performance.



\---



\# Experiential Learning



The learning loop compares predicted consequences with observed consequences.



```mermaid

flowchart LR



&#x20;   A\["Counterfactual Prediction"] --> B\["Selected Action"]



&#x20;   B --> C\["Observed Outcome"]



&#x20;   A --> D\["Expected"]



&#x20;   C --> E\["Actual"]



&#x20;   D --> F\["Prediction Error"]

&#x20;   E --> F



&#x20;   F --> G\["Lesson"]



&#x20;   G --> H\["Hindsight Retain"]



&#x20;   H --> I\["Future Recall"]

```



For example:



```text

Expected resolution:

25 minutes



Observed resolution:

34 minutes



Prediction error:

9 minutes

```



The resulting lesson becomes part of future experiential retrieval.



\---



\# Failure as Experience



EDResolve does not only remember successful interventions.



A failed intervention can also become valuable institutional experience.



```mermaid

flowchart TD



&#x20;   A\["Operational Bottleneck"] --> B\["Intervention"]



&#x20;   B --> C\["Failure"]



&#x20;   C --> D\["Failure Analysis"]



&#x20;   D --> E\["Lesson"]



&#x20;   E --> F\["Hindsight Memory"]



&#x20;   F --> G\["Future Candidate Evaluation"]



&#x20;   G --> H\["Potentially Avoid Repetition"]

```



This is important for an experiential system:



> \*\*A failure can contain information about where an intervention should not be reused.\*\*



\---



\# Evaluation Strategy



The goal is not simply to measure the final system.



The evaluation should isolate the contribution of memory.



```mermaid

flowchart LR



&#x20;   A\["Stateless Baseline"] --> B\["Memory Recall"]



&#x20;   B --> C\["Memory + Simulation"]



&#x20;   C --> D\["Full Learning Loop"]

```



The evaluation framework is designed around controlled comparisons such as:



| Configuration | Memory | Simulation | Learning |

|---|---:|---:|---:|

| Stateless baseline | No | No | No |

| Memory system | Yes | No | No |

| Memory + simulation | Yes | Yes | No |

| Full EDResolve | Yes | Yes | Yes |



Planned evaluation metrics include:



\- resolution time

\- ED boarding time

\- resolution rate

\- P90 resolution time

\- escalation count

\- resource conflicts

\- memory reuse

\- repeated failed-action rate

\- prediction error

\- learning gain



Experiments should use controlled synthetic scenarios and reproducible seeds.



No real-world performance claim is inferred from synthetic experiments.



\---



\# Synthetic Scenario Suite



The current prototype contains several operational scenario classes:



```text

ICU\_BED\_CLEANING

TRANSPORT\_BOTTLENECK

ALTERNATIVE\_UNIT\_AVAILABLE

COORDINATION\_DEADLOCK

MIXED\_BOTTLENECK

```



These scenarios are designed to stress different parts of the decision pipeline:



```mermaid

flowchart TD



&#x20;   A\["Scenario Suite"]



&#x20;   A --> B\["Bed Bottleneck"]

&#x20;   A --> C\["Transport Bottleneck"]

&#x20;   A --> D\["Alternative Capacity"]

&#x20;   A --> E\["Coordination Deadlock"]

&#x20;   A --> F\["Mixed Bottleneck"]



&#x20;   B --> G\["Candidate Generation"]

&#x20;   C --> G

&#x20;   D --> G

&#x20;   E --> G

&#x20;   F --> G



&#x20;   G --> H\["Constraints"]



&#x20;   H --> I\["Counterfactuals"]



&#x20;   I --> J\["Decision"]



&#x20;   J --> K\["Outcome"]



&#x20;   K --> L\["Learning"]

```



\---



\# Full System Architecture



```mermaid

flowchart TB



&#x20;   subgraph UI\["Presentation Layer"]

&#x20;       R\["React / TypeScript"]

&#x20;   end



&#x20;   subgraph API\["Application Layer"]

&#x20;       F\["FastAPI"]

&#x20;       L\["LangGraph"]

&#x20;   end



&#x20;   subgraph INT\["Intelligence Layer"]

&#x20;       G\["GPT-OSS"]

&#x20;       H\["Hindsight"]

&#x20;   end



&#x20;   subgraph MODEL\["Operational Modeling"]

&#x20;       N\["NetworkX"]

&#x20;       P\["PM4Py"]

&#x20;       X\["XGBoost"]

&#x20;   end



&#x20;   subgraph OPT\["Decision Layer"]

&#x20;       O\["OR-Tools"]

&#x20;       S\["SimPy"]

&#x20;   end



&#x20;   subgraph DATA\["Persistence"]

&#x20;       DB\["PostgreSQL"]

&#x20;   end



&#x20;   R --> F

&#x20;   F --> L



&#x20;   L --> G

&#x20;   L --> H



&#x20;   L --> N

&#x20;   L --> P

&#x20;   L --> X



&#x20;   G --> O

&#x20;   N --> O

&#x20;   P --> O



&#x20;   O --> S

&#x20;   S --> L



&#x20;   L --> DB



&#x20;   H --> L

&#x20;   L --> H

```



\---



\# Data Flow



```mermaid

sequenceDiagram



&#x20;   participant UI as React UI

&#x20;   participant API as FastAPI

&#x20;   participant Agent as LangGraph

&#x20;   participant H as Hindsight

&#x20;   participant LLM as GPT-OSS

&#x20;   participant C as Constraints

&#x20;   participant Sim as SimPy

&#x20;   participant DB as PostgreSQL



&#x20;   UI->>API: Current operational case

&#x20;   API->>Agent: ED operational state



&#x20;   Agent->>Agent: Build world model

&#x20;   Agent->>Agent: Identify bottleneck



&#x20;   Agent->>H: Recall similar experiences

&#x20;   H-->>Agent: Historical experiences



&#x20;   Agent->>LLM: Generate candidate interventions

&#x20;   LLM-->>Agent: Candidate actions



&#x20;   Agent->>C: Validate constraints

&#x20;   C-->>Agent: Feasibility results



&#x20;   Agent->>Sim: Simulate feasible alternatives

&#x20;   Sim-->>Agent: Counterfactual outcomes



&#x20;   Agent->>Agent: Select action

&#x20;   Agent->>DB: Persist decision trace



&#x20;   Agent->>Agent: Observe outcome

&#x20;   Agent->>Agent: Calculate prediction error



&#x20;   Agent->>H: Retain completed experience



&#x20;   Agent-->>API: Decision + evidence + trace

&#x20;   API-->>UI: Explainable decision view

```



\---



\# Auditability



Each major stage produces structured information that can be exposed through the interface.



```mermaid

flowchart TD



&#x20;   A\["State"] --> B\["World Model"]

&#x20;   B --> C\["Bottleneck"]

&#x20;   C --> D\["Memory"]

&#x20;   D --> E\["Candidates"]

&#x20;   E --> F\["Constraints"]

&#x20;   F --> G\["Counterfactuals"]

&#x20;   G --> H\["Decision"]

&#x20;   H --> I\["Outcome"]

&#x20;   I --> J\["Learning"]

```



A judge, developer, or operator should be able to inspect:



\- which experiences were retrieved

\- which candidates were generated

\- which actions were infeasible

\- what the simulator predicted

\- why the selected action had the lowest modeled cost

\- what actually happened

\- what was retained for future decisions



\---



\# Interoperability Boundary



The design anticipates a FHIR-compatible interoperability boundary between hospital data sources and the EDResolve operational model.



```mermaid

flowchart LR



&#x20;   A\["Hospital Information Systems"] --> B\["FHIR-Compatible Boundary"]



&#x20;   B --> C\["EDResolve Operational State"]



&#x20;   C --> D\["World Model"]



&#x20;   D --> E\["Decision + Simulation + Memory"]



&#x20;   E --> F\["Human Operational Review"]

```



FHIR is treated as an interoperability boundary, not as the internal reasoning mechanism.



\---



\# Safety and Scope



EDResolve is an \*\*operational decision-support research prototype\*\*.



It is not intended to:



\- diagnose patients

\- prescribe medication

\- recommend clinical treatment

\- replace clinicians

\- autonomously make clinical decisions

\- claim regulatory approval

\- represent a production hospital information system



The current evaluation environment is synthetic.



A production deployment would require domain-specific validation, security, privacy protection, governance, human oversight, interoperability validation, and appropriate regulatory assessment.



\---



\# Repository Structure



```text

ED Resolve/

│

├── backend/

│   │

│   ├── agent/

│   │   ├── \_\_init\_\_.py

│   │   ├── state.py

│   │   ├── prompts.py

│   │   ├── nodes.py

│   │   ├── graph.py

│   │   ├── decision.py

│   │   └── outcome.py

│   │

│   ├── memory/

│   │   └── hindsight\_memory.py

│   │

│   └── simulation/

│       ├── \_\_init\_\_.py

│       ├── models.py

│       ├── actions.py

│       ├── constraints.py

│       ├── ed\_simulator.py

│       └── metrics.py

│

├── data/

│   └── synthetic/

│

├── experiments/

│

├── frontend/

│

├── .env

├── .gitignore

└── README.md

```



\---



\# Development Setup



\## Requirements



\- Python 3.13+

\- Node.js

\- Hindsight

\- Groq API access for GPT-OSS

\- PostgreSQL



\## Backend



```powershell

python -m venv .venv

.venv\\Scripts\\Activate.ps1

```



Install the current backend dependencies:



```powershell

pip install hindsight-client hindsight-api groq langgraph fastapi uvicorn pydantic simpy networkx pandas numpy scipy sqlalchemy psycopg\[binary] ortools pytest

```



\---



\# Environment Variables



Create a local `.env`:



```env

GROQ\_API\_KEY=your\_groq\_api\_key



HINDSIGHT\_API\_URL=http://localhost:8888

HINDSIGHT\_API\_KEY=



HINDSIGHT\_BANK\_ID=edresolve



EDRESOLVE\_REASONING\_MODEL=openai/gpt-oss-120b

```



Never commit credentials or `.env` to Git.



\---



\# Running Hindsight



Start the local Hindsight service:



```powershell

hindsight-api

```



The local development configuration uses:



```text

http://localhost:8888

```



\---



\# Running the Synthetic Simulation



```powershell

python -m backend.simulation.run\_counterfactuals

```



Generated synthetic experiment data is stored under:



```text

data/synthetic/

```



\---



\# Engineering Principles



\### Memory is contextual



Past experience is evidence, not an instruction.



\### Feasibility is deterministic



The LLM cannot override hard operational constraints.



\### Simulation precedes selection



Candidate interventions are evaluated before final selection.



\### Failures are retained



Unsuccessful interventions can become future negative experience.



\### Decisions are auditable



The system preserves the path from state to decision to outcome.



\### Evaluation is ablation-driven



The contribution of memory should be measured against controlled baselines.



\---



\# Current Project Status



\## Implemented



\- Operational state models

\- Bottleneck fingerprinting

\- Hindsight integration

\- Hindsight recall

\- GPT-OSS candidate generation

\- Constraint validation

\- SimPy counterfactual simulation

\- Deterministic action selection

\- Expected-vs-actual analysis

\- Experience construction

\- LangGraph orchestration foundation



\## In Development



\- Complete end-to-end learning loop

\- Hindsight retention in live execution

\- Repeated-episode learning experiments

\- Ablation framework

\- PostgreSQL persistence

\- React / TypeScript interface

\- Decision-trace visualization

\- Memory-learning visualization



\---



\# Research Question



EDResolve explores a broader question:



> \*\*Can an operational agent reuse institution-specific experience, test that experience against a changing environment, and reduce repeated decision failures over time?\*\*



The architecture therefore moves beyond:



```text

Prompt → Answer

```



toward:



```mermaid

flowchart LR



&#x20;   A\["State"] --> B\["Experience"]

&#x20;   B --> C\["Reasoning"]

&#x20;   C --> D\["Counterfactual Evaluation"]

&#x20;   D --> E\["Decision"]

&#x20;   E --> F\["Outcome"]

&#x20;   F --> G\["Learned Experience"]

&#x20;   G --> B

```



The system is designed around the idea that \*\*experience should become an active computational resource for future decisions\*\*.



\---



\# License



This project is intended to use the MIT License.



See `LICENSE` for the complete license text.

