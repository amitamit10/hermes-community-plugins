# פערי פיצ׳רים — ספקי חיפוש מול GOAT

נכון ל־9 באוקטובר 2026. הדירוג מתייחס לפער בממשק ובנתיבים הקיימים, לא לכל מה שאפשר לבנות סביבם.

## קו בסיס והנחות

- ארבעת הכלים הציבוריים ב־`goat-web` הם `goat_search`, `goat_extract`, `goat_crawl`, `goat_probe`. החיפוש הוא DDG HTML; החילוץ הוא HTML סטטי דרך parser מצומצם; הסריקה היא same-origin, סינכרונית ומוגבלת לעומק 2 ול־10 עמודים. אין ב־4 הכלים עצמם חיפוש ורטיקלי או rendering של JavaScript.
- URL gate בודק יעדים ציבוריים ומעברים, וה־paid gate מחזיר `MISSING_CONFIG` בלי fallback שקט. `browser_exec` של Hermes כבר מאפשר לפתוח/לרנדר דף יחיד, ולכן JS לדף בודד אינו פער; פער הוא חיבור rendering, פעולות חילוץ וסריקה רחבה ל־GOAT.
- `free_stack.py` כולל SearXNG מקומי, Wikipedia ו־DDG. הלקוח של SearXNG שולח כרגע רק `q` ו־`format=json`; ברירת המחדל היא `localhost:8888`. שרשרת fallback מפורשת: SearXNG → Wikipedia → DDG.
- `AnySearchClient` כבר כולל חיפוש כללי/ורטיקלי, גילוי תתי־תחומים, `batch_search` של 1–5 וחילוץ URL בודד. בקוד נפרד קיימים גם client adapters ל־Exa/Tavily/Firecrawl/You, אך `plugin.yaml` הציבורי חושף רק את ארבעת הכלים לעיל. לכן מסומנים בנפרד פערי **יכולת** ופערי **חשיפה/ניתוב**. ה־Serper adapter נשאר במכוון לא מוגדר עד לאימות endpoint/auth/schema.

**סיווג:** `חינם-אפשרי` = אפשר להוסיף על בסיס הכלים/מודל/שירות חינמי; `דורש מפתח` = ספק API ממוסמך, גם אם יש free credits; `דורש self-host` = צריך מופע SearXNG בשליטתנו; `לא-רלוונטי` = לא כדאי לרדוף אחרי parity אצל הספק הזה. **עדיפות:** P1 גבוהה, P2 בינונית, P3 נמוכה.

## טבלת פערים לפי ספק

| ספק | מה כבר יש לנו | פערים בפועל מול היכולת של הספק (סיווג · עדיפות) |
|---|---|---|
| **Exa** | client spike תומך `search_type`, `contents` ו־`/contents` למזהים; לא חשוף דרך ארבעת הכלים. | **Deep Search עם סינתזה/תשובה ו־structured output**, וכן חיפוש `news`/`publication` (כולל מאמרים), include/exclude domains ותאריכי פרסום — אין שדות/route ציבורי של GOAT לכך: `דורש מפתח · P1` לתשובה/פילטרים, `P2` לקטגוריות. `contents` למזהים קיים ב־client אך אינו batch-extract חשוף לכלי: פער חשיפה `דורש מפתח · P2`. חיפוש תמונות אינו יתרון מתועד של Exa: `לא-רלוונטי · P3`.[1] |
| **Tavily** | `TavilyClient` כבר כולל search עם options, חילוץ עד 20 URLs ו־crawl, אבל אינו כלי ציבורי מחובר. | **LLM answer**, תחומי `news`/`finance`, הוספת תמונות, פילטרים לפי domain/date — חסרים מהסכמה הציבורית; ניתן להעביר חלקם דרך adapter קיים, לכן זה בעיקר פער חשיפה/ולידציה: `דורש מפתח · P1` לתשובה, `P2` ליתר. Batch-extract ו־crawl כבר קיימים ב־adapter; אין לספור אותם ככתיבת client מחדש, רק כניתוב למשתמש: `דורש מפתח · P2`.[2][3][4] |
| **Firecrawl** | `FirecrawlClient` כולל scrape/crawl עם options כלליים; `goat_extract` ו־`goat_crawl` הקיימים סטטיים ומוגבלים. | **JS rendering מלא בתוך extract/crawl, actions/interact** (wait/click/write/scroll/JS), **batch LLM structured extract** דרך `/extract`, ו־crawl אסינכרוני עם webhooks/עדכוני עמוד — לא מחוברים ל־GOAT. `דורש מפתח · P2`. יש webhook events גם ל־batch scrape; נדרש גם endpoint מקבל מאובטח אצלנו. פעולת JS של דף יחיד כבר מכוסה ב־`browser_exec`, ולכן לא לספור אותה כפער עצמאי.[5][6][7] |
| **Serper** | `SerperClient` הוא scaffold בלבד: דורש endpoint, auth header ו־payload builder מפורשים; במקורות המקומיים הם עדיין מסומנים לא מאומתים, ולכן אין חיבור פעיל. | **Google SERP ורטיקלי ל־Images/News/Scholar** — לא קיים ב־DDG/GOAT: `דורש מפתח · P2`. האתר הרשמי מציג גם Maps/Places/Videos/Shopping/Patents; להתחיל רק מוורטיקלים שבאמת נדרשים. אימות endpoint/auth/payload הוא gate לפני מימוש, לא להעתיק פרטים ממקור צד שלישי.[8] |
| **You.com** | ה־adapter המקומי מכסה רק `search(query)`; יש מסלול MCP חינמי נפרד לחיפוש, לא ל־Answer/Research/Contents. | **Answer API ו־Research API עם תשובה מצוטטת**, כולל מחקר רב־שלבי/רקע; בנוסף חיפוש Web+News עם freshness ו־domain allow/deny, ו־Contents לעד 10 URLs — אינם route ב־GOAT: `דורש מפתח · P1` ל־Answer/Research, `P2` ל־filters ו־batch contents. MCP חינמי הוא נתיב נפרד ומוגבל, לא fallback סמוי ל־API ממוסמך.[9][10][11][15] |
| **AnySearch** | זהו נתיב router קיים: אנונימי/אופציונלית עם מפתח; vertical discovery כולל academic, `batch_search` עד 5 ו־extract לעמוד יחיד. | **אין פער** ב־batch-search או חיפוש academic כללי — הם כבר קיימים. אין בחוזה הנוכחי Answer API, image/news SERP, batch-extract או crawl/webhooks. תשובה אפשר לייצר מקומית באמצעות ה־LLM והמקורות הקיימים (`חינם-אפשרי · P1`); איסוף כמה URLs אפשר לפצל לקריאות extract מקבילות (`חינם-אפשרי · P2`), אך זה אינו endpoint batch-native. לתוצאות Images/News ייעודיות אין צורך להרחיב דווקא את AnySearch: `לא-רלוונטי · P3`; להשתמש ב־SearXNG/Serper לפי הצורך.[12] |
| **SearXNG** | קיים לקוח חיפוש ב־free stack, אך הוא מעביר רק query כללי; ההפעלה האמינה/JSON מיועדת למופע בשליטתנו. | חשיפת `categories`, `time_range`, `language` ו־engine selection תוסיף **News/Images/Scientific publications** לפי המנועים שהוגדרו; time-range נתמך רק במנועים שתומכים בו. `דורש self-host · P1` לפילטרי זמן ו־`P2` לקטגוריות. domain-filtering אינו שדה אחיד: אפשר לנסות `site:` (`חינם-אפשרי · P2`), אך התוצאה תלויה בכך שמנוע המקור יכבד אותו. מופעים ציבוריים עשויים לכבות JSON.[13][14] |
| **DDG** | מספק חיפוש Web חינמי ומסלול fallback; parser הקיים מחזיר כותרת/URL/snippet של תוצאות כלליות. | חיפוש Images/News/Scholar, filters, Answer API או SERP-history אינם חלק מהחוזה הנוכחי; parser ה־HTML שולח `q` בלבד. לא כדאי להרחיב scraping של HTML שברירי כדי לחקות אנדפוינטים ורטיקליים: `לא-רלוונטי · P3`; להשאיר כ־fallback כללי (הקוד המקומי: `goat_tools.py`). |

## חמשת הפערים שכדאי לסגור קודם

| # | פער מוצרי | המסלול המומלץ | סיווג | עדיפות |
|---:|---|---|---|---|
| 1 | **תשובת AI/Research עם citations אמיתיים** במקום snippets בלבד. | להוסיף `goat_answer` שמסכם את תוצאות החיפוש/החילוץ הקיימות ומחזיר URLs; אפשר להתחיל עם ה־LLM המקומי. אם נדרשת תשובת ספק ב־round trip יחיד: You Answer/Research, Tavily `include_answer` או Exa Deep. | `חינם-אפשרי` ל־MVP; `דורש מפתח` לתשובת ספק | **P1** |
| 2 | **פילטרים מובנים**: domain allow/deny, זמן, שפה וקטגוריה. | להוסיף schema ל־router ולהעביר אותו ל־SearXNG (`time_range`/categories) או ל־Exa/Tavily/You; להחזיר במפורש אילו פילטרים באמת נתמכו. | `דורש self-host` דרך SearXNG; `דורש מפתח` דרך APIs | **P1** |
| 3 | **חיפוש Images/News/Scholar אמיתי** עם תוצאות מותאמות לסוג. | SearXNG categories כמסלול free-first; Serper עבור Google Images/News/Scholar. AnySearch academic כבר קיים ואינו צריך להיבנות מחדש. | `דורש self-host` ל־SearXNG; `דורש מפתח` ל־Serper | **P2** |
| 4 | **Extract/crawl דינמי**: JS render, פעולות page ו־schema extraction. | להשאיר `browser_exec` לדף בודד; אם צריך API אחיד שמחבר actions ל־crawl ולהחזרה מובנית, לחבר Firecrawl עם allowlist/מגבלות קיימות ולשמור על URL gate. | `דורש מפתח` | **P2** |
| 5 | **Batch-extract ו־crawl jobs אסינכרוניים** עם אירועי page/completed. | לחשוף את batch של Tavily שכבר כתוב ב־adapter; להוסיף consumer ל־Firecrawl webhooks רק אם באמת דרוש crawl מעבר ל־10 עמודים. | `דורש מפתח`; fan-out מקומי אפשרי בחינם אך פחות יעיל | **P2** |

### נמוך מה־Top-5

- **SERP-history** אינו יכולת ייחודית שמצאנו אצל אחד מהספקים או במימושים הקיימים. אם נדרש audit trail, אפשר לשמור מקומית timestamp, ספק, query ומזהי/URLs שהוחזרו — `חינם-אפשרי · P3`; לא לשמור snippets/תוכן כברירת מחדל, ולהגדיר retention כדי לא להפוך היסטוריית חיפוש למאגר רגיש.
- אין צורך לממש כל יכולת מכל ספק. ל־free-first, שני צעדי ROI ברורים הם חשיפת מסנני SearXNG וחיבור `goat_answer` עם citations; שימוש בספק keyed צריך להישאר בחירה מפורשת ולעמוד ב־`MISSING_CONFIG` ללא fallback שקט.

## מקורות פנימיים שנבדקו

- `goat-web/plugins/goat-web/goat_tools.py` ו־`plugin.yaml` — ארבעת הכלים, גבולות crawl וה־DDG parser.
- `adapters/free_stack.py`, `free_search.py`, `search-fallback-chain.md` — free stack, פרמטרי הקריאה בפועל וכללי router.
- `adapters/anysearch_adapter.py`, `tavily_adapter.py`, `exa_adapter.py`, `firecrawl_adapter.py`, `serper_you_adapter.py` — מה כבר קיים ב־client adapters.
- `goat-ultimate/registry/capabilities.json` ו־`references/paid-adapters.md` — paid gate, מצב אינטגרציה ואימות ספקים. בפרט, Serper נשאר לא מאומת.

## Sources

[1] https://exa.ai/docs/reference/search
[2] https://docs.tavily.com/documentation/api-reference/endpoint/search
[3] https://docs.tavily.com/documentation/api-reference/endpoint/extract
[4] https://docs.tavily.com/documentation/api-reference/endpoint/crawl
[5] https://docs.firecrawl.dev/advanced-scraping-guide
[6] https://docs.firecrawl.dev/webhooks/overview
[7] https://docs.firecrawl.dev/api-reference/endpoint/extract
[8] https://serper.dev
[9] https://you.com/docs/api-reference/answer/v1-answer
[10] https://you.com/docs/api-reference/research/v1-research
[11] https://you.com/docs/api-reference/search/v1-search
[12] https://raw.githubusercontent.com/anysearch-ai/anysearch-mcp-server/main/README.md
[13] https://docs.searxng.org/dev/search_api.html
[14] https://docs.searxng.org/user/configured_engines.html
[15] https://you.com/docs/api-reference/contents
