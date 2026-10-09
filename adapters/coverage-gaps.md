# מפת כיסוי בדיקות, ביצועים ודוגמאות

## שיטה ותוצאה קצרה

נסקרו כל קובצי `*.py` שאינם `test_*.py`: 23 מודולי מימוש (6 ב-`goat-browser-staging`, 17 ב-`goat-packs`) וכן סקריפט benchmark אחד. קובצי הטסטים עצמם נחשבו ראיה לכיסוי, לא מודולי יעד.

- **טסט ייעודי**: קובץ בדיקה ממוקד שמייבא/בודק את המודול.
- **Benchmark**: בדיקת ביצועים שמפעילה את המודול; fuzzing או בדיקות פונקציונליות אינם benchmark.
- **דוגמת שימוש**: דוגמה תיעודית קונקרטית לממשק הציבורי של המודול. דוגמאות לכלי GOAT ברמת ה-handler, תרחיש RSS בלי קריאה ל-API של המודול, וכתובות API שמופיעות ב-docstring אינם נחשבים דוגמאות שימוש למודולי עזר/מתאמים.

במודולי המימוש: **23/23** עם טסט ייעודי, **1/23** עם benchmark, **4/23** עם דוגמת שימוש. פערי benchmark: 22; פערי דוגמאות שימוש: 19.

## `goat-browser-staging`

| מודול | טסט ייעודי | Benchmark | דוגמת שימוש | חוסרים |
|---|---|---|---|---|
| `plugins/goat-web/__init__.py` | יש — `tests/test_plugin_wiring.py` | חסר | יש — דוגמאות קריאה לכלי GOAT ב-`references/examples.md` | benchmark |
| `plugins/goat-web/adapters.py` | יש — `tests/test_adapters.py` | חסר | חסר — אין דוגמת קריאה ישירה לממשקי העזר | benchmark, דוגמה |
| `plugins/goat-web/goat_tools.py` | יש — `tests/test_goat_tools.py` | חסר | יש — דוגמאות לכלים ב-`references/examples.md` | benchmark |
| `plugins/goat-web/url_gate.py` | יש — `tests/test_ssrf_block.py`, `tests/test_redirect_gate.py`, `tests/test_gate_fuzz.py` | יש — `goat-packs/bench_gate.py` מודד את `check_url` ו-`check_redirect`; תוצאות ב-`goat-packs/bench-results.md` | חסר — יש דוגמת חסימת URL ברמת הכלי, לא דוגמת שימוש ישירה ל-API של ה-gate | דוגמה |
| `scripts/audit_staging.py` | יש — `tests/test_missing_env.py`, `tests/test_secret_scan.py`, `tests/test_traversal.py` | חסר | יש — פקודת הרצה ותוצאה ב-`references/qa-report.md` | benchmark |
| `scripts/fuzz_gate.py` | יש — `tests/test_gate_fuzz.py` | חסר — fuzzer אינו benchmark ביצועים | יש — פקודת הרצה ותוצאה ב-`references/qa-report.md` | benchmark |

## `goat-packs` — מודולי מימוש

| מודול | טסט ייעודי | Benchmark | דוגמת שימוש | חוסרים |
|---|---|---|---|---|
| `answer_synth.py` | יש — `test_answer_synth.py` | חסר | חסר | benchmark, דוגמה |
| `anysearch_adapter.py` | יש — `test_anysearch.py` | חסר | חסר | benchmark, דוגמה |
| `browser_tier.py` | יש — `test_browser_tier.py` | חסר | חסר | benchmark, דוגמה |
| `crawl_pro.py` | יש — `test_crawl_pro.py` | חסר | חסר | benchmark, דוגמה |
| `deep_verticals.py` | יש — `test_deep_verticals.py` | חסר | חסר — ה-URLs ב-docstring הם הפניות API, לא דוגמת שימוש | benchmark, דוגמה |
| `donsetch_adapter.py` | יש — `test_donsetch.py` | חסר | חסר | benchmark, דוגמה |
| `exa_adapter.py` | יש — `test_exa.py` | חסר | חסר | benchmark, דוגמה |
| `firecrawl_adapter.py` | יש — `test_firecrawl.py` | חסר | חסר | benchmark, דוגמה |
| `free_search.py` | יש — `test_free_search.py` | חסר | חסר | benchmark, דוגמה |
| `free_stack.py` | יש — `test_free_stack.py` | חסר | חסר | benchmark, דוגמה |
| `free_verticals.py` | יש — `test_free_verticals.py` | חסר | חסר | benchmark, דוגמה |
| `native_tier.py` | יש — `test_native_tier.py` | חסר | חסר | benchmark, דוגמה |
| `rss_watcher.py` | יש — `test_rss_watcher.py` | חסר | חסר — `examples2.md` מציג תרחיש RSS, אך לא קריאה ל-API של ה-watcher | benchmark, דוגמה |
| `search_filters.py` | יש — `test_search_filters.py` | חסר | חסר | benchmark, דוגמה |
| `serper_you_adapter.py` | יש — `test_serper_you.py` | חסר | חסר | benchmark, דוגמה |
| `ssrf_guard.py` | יש — `test_pack_ssrf.py` | חסר | חסר | benchmark, דוגמה |
| `tavily_adapter.py` | יש — `test_tavily.py` | חסר | חסר | benchmark, דוגמה |

## סקריפט עזר ב-`goat-packs`

| קובץ | טסט ייעודי | Benchmark | דוגמת שימוש | חוסרים |
|---|---|---|---|---|
| `bench_gate.py` | חסר — לא נמצא `test_bench_gate.py` | יש — זהו harness לבנצ'מרק; הוא מודד את `goat-browser-staging/plugins/goat-web/url_gate.py`, לא את מודולי `goat-packs` | חסר — `bench-results.md` מציג תוצאות אך לא הוראת הרצה כדוגמת שימוש | טסט, דוגמה |

## רשימת החוסרים

- **Benchmark חסר ל-22 מודולי מימוש:** חמשת מודולי `goat-browser-staging` למעט `url_gate.py`, וכל 17 מודולי `goat-packs`.
- **דוגמת שימוש חסרה ל-19 מודולי מימוש:** `adapters.py`, `url_gate.py`, וכל 17 מודולי `goat-packs`. דוגמאות `examples2.md` הן fixtures/תרחישים ברמת הכלים ואינן מראות שימוש ישיר בממשקי המתאמים.
- **טסט ודוגמת שימוש חסרים ל-harness `bench_gate.py` עצמו.**
- **לא נמצא פער טסט למודולי המימוש.** ב-`goat-browser-staging` יש 10 קובצי בדיקה; ב-`goat-packs` יש 17. `test_manifest.py` בודק את manifest ולא משויך למודול Python.
