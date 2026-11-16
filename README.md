AGRION
From Earth observation to smarter agricultural decisions
NASA Space Apps Challenge 2026 · Agricultural Decision Support · Earth Data & AI

Explore AGRION · NASA POWER · Project Submission Guide
</div>Overview
AGRION is an agricultural decision-support project that seeks to make scientific and environmental information easier to use in everyday farming decisions. It brings together NASA weather data, agronomic references, crop simulation, artificial intelligence, and an experimental, ESP32-based weather station.

Rather than presenting a single generic recommendation, AGRION is designed to help farmers explore their location, investigate crop options, understand relevant conditions, and compare planting strategies with clearer scientific context.

Public website: https://agrion.earth/
Prototype disclosure: AGRION is a hackathon prototype. Its web experience, scientific backend, and hardware demonstration are at different stages of integration. Results should be interpreted as decision-support information, not guaranteed harvest forecasts or substitutes for field measurements and agronomic advice.

The problem
Choosing what to plant and when to plant it involves many interacting factors: temperature, rainfall, water availability, soil characteristics, crop requirements, previous crops, and economic context. The information needed to evaluate these factors often lives in different platforms, datasets, and scientific publications.

AGRION's goal is to bring those sources closer to the farmer through an accessible experience while preserving a distinction between observed data, modeled results, research evidence, and future capabilities.
What AGRION brings together
Area	Purpose
My Property	A location-centered experience for agricultural property information and crop planning.
Agricultural discovery	Explore agricultural questions through guided interactions, including a voice-enabled AI discovery experience.
Crop information	Consult crop requirements and relevant agronomic references.
Crop and rotation comparison	Support the comparison of potential crop choices and crop sequences using documented evidence.
Weather and climate	Combine historical climate information with weather forecast services where available.
Crop simulation	Model crop development and water balance in explicit scenarios using AquaCrop-OSPy.
Experimental weather station	Capture local environmental readings using an ESP32-based physical prototype.


These are the project's product areas and technical building blocks; their presence in this table does not mean every feature is already connected end to end in the public interface.
How it works
AGRION is organized around three complementary layers:
Farmer / Web Experience
  |
  +-- Property and geographic context
  +-- Agricultural discovery (form / voice-assisted interaction)
  +-- Crop information, comparisons, and planning views
  |
Scientific and Data Services
  |
  +-- NASA POWER historical weather data
  +-- Weather forecast providers
  +-- Agronomic knowledge and crop requirements
  +-- FAO methodologies and crop simulation
  +-- Economic and geographic reference data
  |
Physical Demonstrator
  |
  +-- ESP32 weather station
      +-- Temperature and humidity
      +-- Rain detection
      +-- Wind-driven DC motor signal
      +-- Local readings and optional telemetry
Application architecture
- Flask web application: user-facing experience and agricultural discovery flow (development service on port 8000).
- FastAPI scientific backend: catalogs, climate and agricultural indicators, economic information, and crop simulation endpoints (development service on port 8001).
- Vertex AI: AI-enabled discovery and access to external research/search capabilities within the project design.
- Map and location services: MapTiler is used for satellite-map imagery and address search.
- Browser-side data: some prototype registration and discovery information is handled locally in the browser.
Integration status: the documented development snapshot did not yet have a complete Flask/assistant-to-FastAPI integration. Backend functionality should not be assumed to be available through every public-facing screen.
NASA data: an essential part of AGRION
NASA POWER — integrated
AGRION uses NASA POWER historical meteorological information to provide a climate-data foundation for agricultural indicators and crop simulation. Historical weather series are processed into the variables and inputs required by the scientific pipeline, including reference evapotranspiration calculations using the FAO-56 methodology.
- NASA POWER documentation
- NASA POWER API documentation
Other NASA resources — research or future integration
Additional Earth-observation resources such as SMAP, GPM, HLS, and GEOS-FP have been evaluated or identified as potential complements. They should not be described as fully operational AGRION integrations in the 2026 prototype. In the documented development snapshot, GEOS-FP had an access proof of concept only.
Scientific and external data sources
Source / technology	Role in the project
NASA POWER	Historical weather data for climate analysis and simulation inputs.
FAO-56	Reference evapotranspiration methodology.
ECOCROP	Crop environmental requirements and suitability references.
GAEZ	Agroecological suitability and geographic reference layers; targeted consultations.
FAOSTAT	Agricultural statistics and historical national producer-price context.
AquaCrop-OSPy	Python crop-growth and water-balance simulation.
FAO AquaCrop	Scientific basis of the AquaCrop modeling family; distinct from AquaCrop-OSPy and the official FAO 7.3 Python implementation.
Open-Meteo	Weather-forecast fallback provider.
Meteomatics	Weather forecast provider in the weather-data workflow.
MapTiler	Basemap/satellite imagery and location search.
Google Vertex AI	AI-assisted agricultural discovery and search-related capabilities.


A structured agronomic knowledge library complements these sources with scientific publications, crop information, evidence records, and crop-rotation relationships. Not every reference is an automatically updated or live data integration.
Soil-data note
The Harmonized World Soil Database (HWSD v2.2) was researched and downloaded as a candidate soil reference. Its existence in the project's research materials does not imply that measured local soil conditions or a complete HWSD-driven soil simulation are already implemented.
Crop simulation: reproducible scenarios, not promises
The scientific backend has executed a maize scenario using AquaCrop-OSPy 3.0.12, NASA historical climate data, and FAO-56 reference evapotranspiration processing.

One documented test completed 132 simulated days and produced 14.37098 t/ha of simulated dry yield, with a closed water balance and reproducible results for the same explicit weather series. These numbers describe one modeled test scenario, not a real-world prediction for a named farm.

The scenario used declared assumptions for generic soil, initial water, CO₂, and management. Local calibration, measured soil inputs, irrigation scenarios, and additional crop validation remain development work. The project's documented implementation also distinguishes its functioning AquaCrop-OSPy route from the official FAO AquaCrop 7.3 Python distribution, which remained unresolved in that snapshot.
AGRION weather station — physical prototype
The project also includes a physical mini weather-station demonstrator based on an ESP32 DevKit with ESP32-WROOM-32.

Measured or detected signals:
- Temperature and relative humidity: DHT22 sensor.
- Rain presence: FC-37 rain sensor with YL-38-compatible interface.
- Wind-related signal: DC motor rotated by a wind-driven propeller, used as an experimental electrical signal rather than a certified or calibrated wind-speed instrument.
The station includes a breadboard, wiring, and 3D-printed parts developed or adapted for component mounting and the anemometer assembly. Some of these parts originated from a third-party 3D model, which should be credited with its original URL and license in the hardware documentation.

The ESP32 exposes measurements on the local network. When configured with the station key, its firmware is designed to send telemetry to AGRION at five-second intervals.
Hardware note: the physical sensor prototype demonstrates data acquisition. It is not represented as a calibrated meteorological instrument, and production-side telemetry behavior depends on the final deployed configuration.

Current status and limitations
AGRION is a working research and hackathon prototype, not a production-grade agronomic advisory service.

Documented technical progress
- NASA POWER historical data integration.
- Weather forecasting workflow using Meteomatics with Open-Meteo fallback.
- Selected backend environmental/agricultural indicators.
- Crop simulation execution with AquaCrop-OSPy.
- Agronomic research and knowledge-base organization.
- Experimental ESP32 weather-station hardware.
Known limitations and development work
- Complete connectivity between the Flask interface, AI assistant, and FastAPI backend.
- End-to-end validation of all proposed crop-comparison and planning screens.
- Farm-specific soil measurements, calibration, and model validation.
- Additional crops, irrigation configurations, and broader scenario coverage.
- Operational integration of further NASA satellite products.
- Robust deployment, monitoring, authentication, and data-handling practices for production use.
Try AGRION
Live project: agrion.earth

For the challenge, visit the public website to explore the presented experience. Certain scientific capabilities described in this README are implemented in separate development services and may not yet be exposed through the public interface.
Development access
The documented development layout uses:
Service	Local address
Flask web application	http://127.0.0.1:8000
FastAPI scientific API	http://127.0.0.1:8001
AquaCrop simulation endpoint	POST http://127.0.0.1:8001/v1/simulations/aquacrop


Setup instructions: the precise commands, environment variables, dependency files, and repository layout should be documented from the actual published source tree. Credentials and station keys must not be committed to version control. No unverified installation commands are provided here.
Demonstration and project materials
- Live experience: https://agrion.earth/
- NASA Space Apps project demo: Add the final public video URL.
- Project screenshots: Add screenshots or GIFs from the actual deployed system.
- Hardware, 3D models, and assembly: Add the public folder or repository subdirectory and third-party model attribution.
AI use and transparency
AGRION incorporates AI-related functionality as a part of its agricultural discovery concept, including Vertex AI. AI tools have also supported development and documentation workflows.

AI-generated code, assets, audio, or other materials must be identified in the corresponding source comments, descriptions, metadata, or visible labels as applicable. Any AI-generated images or video used in the NASA Space Apps submission should be visibly labeled. NASA branding must not be reproduced or modified in AI-generated content.

AI output is not treated as a substitute for scientific validation, field data, or documented source evidence.
Credits, licensing, and acknowledgments
AGRION was developed as a project for the NASA Space Apps Challenge 2026.

The team acknowledges the publicly available research, methods, datasets, and services described above, including NASA POWER, FAO, the AquaCrop-OSPy maintainers, and the relevant weather, mapping, and AI service providers.

Third-party assets: every externally sourced image, sound, code component, 3D design, and dataset should retain attribution and be used under its applicable license. In particular, include the original author, source URL, and license for the third-party anemometer 3D model.

Team: Add the official team name and member names.
Challenge: Add the exact official 2026 challenge title.
License for original AGRION code: Specify only after selecting a repository license.

Disclaimer: AGRION is an independent hackathon project. References to NASA and other data providers do not imply their sponsorship, endorsement, or certification of the project's agricultural recommendations.
