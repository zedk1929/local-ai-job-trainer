# Survey Cleaner Baseline Evaluation: Labeling Notes & Taxonomy

> **Notice on Dataset Nature**: This dataset (`dataset.csv`) contains 60 fictional, AI-drafted survey responses plus 1 blank row. It is intended for exploratory development and pipeline verification only. It is **not** an independent benchmark, verified human gold standard, or final holdout test set. All annotations represent initial development labels and are subject to human review.

---

## 1. Job Taxonomy Definition

The Survey Cleaner task uses a fixed 4-category taxonomy tailored to campus café operations:

| Category ID | Display Name | Scope & Definition |
| :--- | :--- | :--- |
| `drink_quality` | Drink Quality | Taste, temperature, espresso extraction, milk texture, bean freshness, flavor profile, or recipe accuracy. *(Note: food or bakery items are excluded unless drinks are mentioned).* |
| `price` | Price & Value | Cost of items, discounts, value for money, perceived affordability, surcharges, or pricing policies. |
| `service` | Staff & Service | Speed of service, barista friendliness, accuracy of order fulfillment, attentiveness, wait times, or staff conduct. |
| `seating` | Atmosphere & Seating | Table availability, noise levels, seating comfort, WiFi, power outlets, cleanliness of seating area, lighting, temperature, or overall store atmosphere. |

---

## 2. Coding Rules

The baseline model is prompted with the following explicit coding rules:

1. **Multiple Topics**: Assign all relevant topics that are explicitly mentioned or strongly implied by the customer. A single response may receive 0, 1, 2, 3, or all 4 topics.
2. **Mixed Sentiment**: If the comment mentions both positive and negative aspects across any topics (e.g., *"Coffee was great but the line was huge"*), mark overall sentiment as `mixed`.
3. **Unclear Responses & Reviews**: If the customer expresses confusion/uncertainty, or the text is incomprehensible/gibberish, mark sentiment as `unclear` and set `needs_review: true`.
4. **Factual Grounding**: Do not infer unmentioned details or extrapolate facts beyond what the user wrote.
5. **Safety & Hygiene Review Trigger**: Set `needs_review: true` if the customer reports an unresolved physical safety, harassment, contamination, or severe hygiene issue (e.g., foreign objects in food/drink, chemical odors, physical threats, broken glass).

---

## 3. Pre-Inference Label Inspection & Ambiguities

Before running inference, all 61 rows in `dataset.csv` were inspected against the schema and coding rules. No syntactic or taxonomy membership errors were found. The dataset is frozen as of SHA-256 `20b384cd00a709c8cc0b70c34996b18845041dd1a23156b00b09da53149d19bc`.

### Questionable / Ambiguous Labels Flagged for Human Review

1. **DEV_38**: *"Vibes are immaculate here! Huge shoutout to the baristas for keeping the energy so high."*
   - Ground Truth: `service; seating`, `positive`, `needs_review: false`.
   - *Ambiguity*: "Vibes are immaculate" is coded as `seating` (atmosphere). An alternative interpretation is general store sentiment with no specific physical seating mentioned.
2. **DEV_39**: *"Eight bucks for avocado toast with zero seasoning is a certified rip-off."*
   - Ground Truth: `price`, `negative`, `needs_review: false`.
   - *Ambiguity*: Mentions food quality ("zero seasoning") alongside high cost. Because the taxonomy only provides `drink_quality` and lacks a `food_quality` category, food flavor is omitted and only `price` is coded. Models might over-generalize food to `drink_quality`.
3. **DEV_42**: *"Comfy seeting and reliable wfi, but the pastrees are way overpiced."*
   - Ground Truth: `price; seating`, `mixed`, `needs_review: false`.
   - *Ambiguity*: Pastries are overpriced (`price`), seating and wifi are comfy (`seating`). Food quality is again unmapped due to taxonomy constraints.
4. **DEV_44**: *"Honestly, the house drip coffee is not bad at all compared to the campus dining hall."*
   - Ground Truth: `drink_quality`, `positive`, `needs_review: false`.
   - *Ambiguity*: "Not bad at all" is colloquial faint praise. Depending on strictness, this could be construed as `neutral`.
5. **DEV_48**: *"Found a rusty metal staple baked right inside the blueberry muffin. Handed it to the cashier who just tossed it."*
   - Ground Truth: `service`, `negative`, `needs_review: true`.
   - *Ambiguity*: Foreign object in food. Since there is no `food_quality`, it is mapped to `service` (the cashier's reaction and serving tainted food). The model may omit topics entirely or invent a food topic.
6. **DEV_56**: *"Just wondering if anyone knows who was driving that silver sedan parked near the back?"*
   - Ground Truth: `[]`, `unclear`, `needs_review: true`.
   - *Ambiguity*: The text is completely unrelated to café operations. Rule 3 specifies setting `needs_review: true` for incomprehensible comments; this is an off-topic parking query rather than gibberish, but flagged for human supervisor triage.
7. **DEV_57 & DEV_58**:
   - DEV_57: *"Does the campus library across the street validate visitor parking on weekends?"* (`[]`, `neutral`, `needs_review: false`).
   - DEV_58: *"The afternoon sunshine on the sidewalk outside was 72 degrees and gorgeous."* (`[]`, `positive`, `needs_review: false`).
   - *Ambiguity*: Both are completely off-topic comments. DEV_57 is coded `neutral` and DEV_58 is coded `positive`, with neither requiring review because neither reports a hazard nor is incomprehensible.

---

## 4. Per-Response Annotation Catalog

| ID | Text Snippet | Ground Truth Topics | Sentiment | Review? | Rationale |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `DEV_01` | Ethiopian espresso with citrus notes and velvety crema | `drink_quality` | positive | false | Explicit praise of espresso extraction and flavor. |
| `DEV_02` | Bitter, burnt drip coffee sitting since 6am | `drink_quality` | negative | false | Taste and freshness complaint. |
| `DEV_03` | Standard dark roast coffee. Nothing special, tasted okay | `drink_quality` | neutral | false | Middle-of-the-road feedback on coffee taste. |
| `DEV_04` | Cashier exceptionally cheerful, remembered order | `service` | positive | false | Commendation for staff friendliness and competence. |
| `DEV_05` | Waited 20 minutes while baristas chatted | `service` | negative | false | Slow speed of service and staff inattention. |
| `DEV_06` | Cashier swiped card without hello/goodbye, routine | `service` | neutral | false | Routine service interaction with no positive or negative affect. |
| `DEV_07` | $3 for large cold brew is unbeatable deal | `price` | positive | false | Value for money praise. |
| `DEV_08` | Charging extra $1.25 for oat milk is price gouging | `price` | negative | false | Price surcharge complaint. |
| `DEV_09` | Standard city prices, about what you expect | `price` | neutral | false | Typical pricing expectation. |
| `DEV_10` | Cozy velvet armchairs and quiet study nook | `seating` | positive | false | Comfort and quiet atmosphere. |
| `DEV_11` | Freezing AC and hard benches with zero back support | `seating` | negative | false | Physical discomfort and temperature. |
| `DEV_12` | Four small two-top tables along the east wall | `seating` | neutral | false | Purely descriptive factual statement about furniture. |
| `DEV_13` | Silky cappuccino, but $8 is way too expensive | `drink_quality; price` | mixed | false | Good drink quality paired with negative price. |
| `DEV_14` | Delicious vanilla bean latte, surprisingly affordable | `drink_quality; price` | positive | false | Both drink and price are praised. |
| `DEV_15` | Barista crafted gorgeous rosetta with warm smile | `drink_quality; service` | positive | false | Latte art/drink quality plus friendly barista. |
| `DEV_16` | Server dismissive, gave whole milk instead of oat | `drink_quality; service` | negative | false | Order inaccuracy/drink recipe plus poor service attitude. |
| `DEV_17` | Staff wiping tables, booths fantastic for studying | `service; seating` | positive | false | Attentive cleaning staff plus comfortable study booths. |
| `DEV_18` | Sticky tables with dirty mugs, staff made zero effort | `service; seating` | negative | false | Dirty seating area and neglectful staff. |
| `DEV_19` | Comfy booths and fast WiFi, but $7 for tea is ridiculous | `price; seating` | mixed | false | Positive seating/wifi paired with negative price. |
| `DEV_20` | Outstanding cold brew, plenty of sunlight at table | `drink_quality; seating` | positive | false | Great coffee taste and pleasant seating atmosphere. |
| `DEV_21` | Matcha tasted like chalky powder, deafening music | `drink_quality; seating` | negative | false | Bad drink quality and noisy environment. |
| `DEV_22` | Swift turnaround and 15% student discount | `service; price` | positive | false | Fast service and favorable price discount. |
| `DEV_23` | Endless line plus unexpected 18% mandatory fee | `service; price` | negative | false | Long wait and unexpected price surcharge. |
| `DEV_24` | Sweet staff apologized, but Americano lukewarm and sour | `drink_quality; service` | mixed | false | Friendly service (positive) vs bad drink (negative). |
| `DEV_25` | Pour-over exquisite, barista knowledgeable, $9 hurts | `drink_quality; service; price` | mixed | false | Positive drink & service vs negative price. |
| `DEV_26` | Friendly staff, smooth flat whites, cushioned chairs | `drink_quality; service; seating` | positive | false | Positive across drink, service, and seating. |
| `DEV_27` | Overpriced sour drip in cramped noisy basement | `drink_quality; price; seating` | negative | false | Negative across drink, price, and seating. |
| `DEV_28` | Swift polite baristas, great lighting, overpriced drinks | `service; price; seating` | mixed | false | Positive service & atmosphere vs negative price. |
| `DEV_29` | Plush booths, fast staff, fair prices, delicious espresso | `drink_quality; service; price; seating` | positive | false | Universal praise across all four categories. |
| `DEV_30` | Bitter coffee, rude cashier, highway robbery, dirty seats | `drink_quality; service; price; seating` | negative | false | Universal criticism across all four categories. |
| `DEV_31` | Top-tier nitro brew & chairs, sluggish staff & steep prices | `drink_quality; service; price; seating` | mixed | false | Mixed polarity across all four categories. |
| `DEV_32` | $10 burnt latte, cashier rolled eyes at receipt request | `drink_quality; service; price` | negative | false | Criticizes price ($10), drink (burnt), and service (attitude). |
| `DEV_33` | Dark roast is straight jet fuel, got me through finals | `drink_quality` | positive | false | Slang praise for strong, effective coffee. |
| `DEV_34` | Morning crew absolute machines tackling 40-person rush | `service` | positive | false | High praise for staff speed under pressure. |
| `DEV_35` | Second mortgage for cortado and croissant | `price` | negative | false | Hyperbolic complaint about excessive price. |
| `DEV_36` | Perched on freezing radiator because furniture full | `seating` | negative | false | Severe seating capacity shortage. |
| `DEV_37` | Iced mocha totally mid tbh, 90% melted ice water | `drink_quality` | negative | false | Watered down drink quality. |
| `DEV_38` | Vibes are immaculate, baristas high energy | `service; seating` | positive | false | Atmospheric energy and staff enthusiasm. |
| `DEV_39` | $8 for avocado toast with zero seasoning is rip-off | `price` | negative | false | Price rip-off (food quality unmapped). |
| `DEV_40` | Hazelnut brew legit fire, counter homie hooked it up in 30s | `drink_quality; service` | positive | false | Slang praise for great coffee and fast friendly service. |
| `DEV_41` | Expresso unberably sour, capaccino foam compltely flat | `drink_quality` | negative | false | Misspelled text complaining of sour coffee and flat foam. |
| `DEV_42` | Comfy seeting, reliable wfi, pastrees overpiced | `price; seating` | mixed | false | Typos; good seating & wifi vs overpriced pastry. |
| `DEV_43` | Barrista got order totaly wrong and argued | `service` | negative | false | Order mistake and combative staff behavior. |
| `DEV_44` | House drip not bad at all compared to dining hall | `drink_quality` | positive | false | Faint praise / comparison to dining hall. |
| `DEV_45` | Never waited more than 90 seconds for pickup | `service` | positive | false | Speed of fulfillment. |
| `DEV_46` | Not cheap, but cannot complain about leather couches | `price; seating` | mixed | false | Negative price vs positive comfortable seating. |
| `DEV_47` | Jagged shard of green glass in iced latte, gum bleeding | `drink_quality` | negative | **true** | Physical injury and beverage contamination hazard. |
| `DEV_48` | Rusty staple baked inside muffin, cashier tossed it | `service` | negative | **true** | Dangerous foreign object in food item. |
| `DEV_49` | Milk smelled like rancid bleach, felt severely sick | `drink_quality` | negative | **true** | Severe food poisoning / chemical contamination hazard. |
| `DEV_50` | Aggressive person threatening customers, staff did nothing | `service` | negative | **true** | Customer safety and physical violence threat. |
| `DEV_51` | Cracked ceramic mug rim sliced lower lip | `drink_quality` | negative | **true** | Physical laceration hazard from chipped dishware. |
| `DEV_52` | Dead cockroach floating in cold brew, manager dismissed | `drink_quality; service` | negative | **true** | Severe pest contamination and dismissive management. |
| `DEV_53` | Maybe next Tuesday? Not sure if blue one by counter | `[]` | unclear | **true** | Fragmented, incomprehensible query. |
| `DEV_54` | Said twelve then changed to seven, what that means? | `[]` | unclear | **true** | Unclear, ambiguous context requiring clarification. |
| `DEV_55` | Coffee coffee... green umbrella near yellow bike rack? | `[]` | unclear | **true** | Lost-and-found fragment mixed with gibberish. |
| `DEV_56` | Who was driving silver sedan parked near back? | `[]` | unclear | **true** | Off-topic vehicle inquiry flagged for triage. |
| `DEV_57` | Does library across street validate visitor parking? | `[]` | neutral | false | Off-topic question, but grammatically clear and safe. |
| `DEV_58` | Afternoon sunshine outside was 72 degrees and gorgeous | `[]` | positive | false | Off-topic weather observation, clear and safe. |
| `DEV_59` | Asked about beans, cashier scoffed "we do not sell that" | `service` | negative | false | Rude staff interaction and abrupt refusal. |
| `DEV_60` | First visit great pour-over, second visit lukewarm 20 min wait | `drink_quality; service` | mixed | false | Multiline feedback covering drink and speed across 2 visits. |
| `DEV_61` | *(Blank response)* | `[]` | *N/A* | *N/A* | Blank response row testing skip/reporting handling. |
