# IGRM Atlas port-trade vertical — acquisition decision, 2026-08-09

## Decision

The first real Atlas dependency vertical will be built from official joint
country × principal-commodity × Major-Port observations, not inferred from
press salience and not purchased from UN Comtrade.

The latest anchor is the Ministry of Ports, Shipping and Waterways' *Basic Port
Statistics of India 2024-25*, tables 2.1.6 and 2.1.7. The historical parser and
cross-vintage check use the Ministry's 2019-20 GODL-India CSV resources. Both
sources remain `review_required`; no row or derived relation may be published
until the project has a human-signed source-specific rights decision.

This is a source acquisition, not yet an exposure graph. A country × commodity
× port fact is ternary. Splitting it into two binary edges would destroy the
joint meaning. Frozen OGES 0.1.0 therefore remains unchanged and the compiler
emits zero dependency relations until a lossless multi-role observation object
and entity crosswalks are registered.

## What was acquired and mechanically checked

| Vintage | Input | Detail rows | Candidate port observations | Public now? |
| --- | --- | ---: | ---: | --- |
| 2024-25 | Ministry PDF, 243 pages, tables 2.1.6/2.1.7 | 703 | 1,264 positive country–commodity–port cells | No — rights and schema gates remain closed |
| 2019-20 | Two OGD CSV resources, unit checked against Ministry PDF | 233 | 684 positive country–commodity–port cells | No — rights and schema gates remain closed |

The 2024-25 parser derives column geometry separately on every table page,
checks the exact PDF hash and file size, enforces the registered commodity
sequence and reconciles printed row and commodity totals. Source blanks remain
blanks. Seven unloaded rows and one loaded row omit the printed `ALL PORTS`
total; visible port quantities are retained without inventing a row total.
Provider spellings and apparent typos remain untouched pending a separately
registered crosswalk.

The loaded table itself labels the country field `Country of Origin`. IGRM does
not relabel it `destination` without an authoritative semantic resolution.

## Coverage boundary

The table has thirteen columns: two Syama Prasad Mookerjee Port dock systems
and eleven other Major Port Authority columns. It is not a denominator for all
Indian ports. It contains no firm, consignee, supplier, vessel, bill of lading,
shipment, inland state, substitution, inventory, transit time or economic-loss
field. A fiscal association is not a disruption, forecast or causal effect.

## Purchase decision

Do not buy UN Comtrade Premium for this vertical. As retrieved on 2026-08-09,
the UN advertises a free Basic Individual account with up to 100,000 records per
call and 500 calls per day. Premium Individual is USD 2,000 per year and still
states internal-use terms. Comtrade adds partner × HS × period trade breadth,
but it does not by itself supply the port × firm × vessel relationship that
Atlas lacks. Use the free account first and evaluate its exact record coverage,
terms and reproducibility before any purchase.

Commercial spend is eligible only if a provider supplies a bounded pilot that
adds at least one missing joint dimension and permits the intended public
derived use. The two useful quote requests are:

1. historical and current AIS port/berth calls for the declared Indian port
   frame, with vessel identifiers, coverage diagnostics and archive rights;
2. a shipment-level India sample with consignee/shipper, commodity, origin,
   destination and port fields, plus explicit public-derived-output terms.

Kpler/MarineTraffic and S&P Panjiva advertise those respective capabilities,
but publish no usable self-serve price or public-redistribution grant. A sales
demo is evidence of product capability, not permission for IGRM publication.

## Gates to the first real Atlas release

1. Human source-rights review signs or refuses the exact Ministry and OGD uses.
2. Register lossless `dependency_observation` semantics without changing OGES
   0.1.0.
3. Register country, commodity and port entity crosswalks; preserve unmatched
   provider labels and publish denominator coverage.
4. Publish the declared port universe, inclusion rules and excluded non-major
   port scope.
5. Add cross-vintage comparability rules; do not interpret category drift as a
   real flow change.
6. Only then compile rights-cleared observations, evidence bundles and Atlas
   views. Any missing gate renders a predefined limitation or refusal.
7. Add a second live operational lane only after an AIS/PortWatch source passes
   rights, coverage, replay and outage tests.

This vertical is successful when a user can select an official fiscal
country–commodity–port observation, see its exact source page, unit, vintage,
missingness, denominator and transformation, and obtain the same result from a
release-bound compiler. It is not successful merely because the map looks
alive.
