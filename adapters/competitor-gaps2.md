# פערי מתחרים — סבב 2 (GOAT)

**נבדק:** 9 באוקטובר 2026. **היקף:** חבילת GOAT לחיפוש/חילוץ, לא Hermes Agent כולו. המידע החיצוני להלן מבוסס על תיעוד רשמי או repository רשמי; לא נרשמו חשבונות ולא נוצרו מפתחות.

## בסיס ההשוואה

ב־snapshot המקומי, ה־plugin הציבורי חושף `goat_search`, `goat_extract`, `goat_crawl`, `goat_probe`; מתאמי Exa/Tavily/Firecrawl ועזרי `answer_synth.py`, `search_filters.py`, `free_verticals.py` קיימים בקוד אך אינם מחוברים לכלים הציבוריים. שכבת החיפוש החינמית כוללת SearXNG, Wikipedia ו־DDG; לקוח SearXNG מעביר כרגע query ו־JSON בלבד. כלי החילוץ/סריקה הציבוריים מוגבלים לעומת שכבת הספקים, ו־`browser_tier.py` מספק מסלול render לדף יחיד ולא תחליף לסריקת אתר. לכן רוב הפערים הם **חשיפה/ניתוב**, לא היעדר מוחלט של קוד. ראיות מקומיות: `roadmap-gaps.md`, `feature-gaps.md` והמודולים הנזכרים לעיל.

**תוויות היתכנות חינמית:** `חינם-אפשרי` — אפשר לממש על בסיס קוד/שירות ציבורי ללא מפתח ספק; `חינם-מוגבל` — מסלול ציבורי או self-host עם מגבלת מכסה/תפעול; `דורש מפתח/תשלום` — נדרש API ספק; `לא-יעד` — אינו API פעיל או שהעלות/הערך אינם מצדיקים parity.

## Top 6 — פערים מומלצים

| # | פער | מה לסגור ב־GOAT | היתכנות חינמית |
|---:|---|---|---|
| 1 | **תשובה מצוטטת מעל תוצאות חיפוש** | לרשום את `goat_answer` הקיים ככלי ציבורי, עם תשובה קצרה, קישורים שמקורם בתוצאות, והפרדה בין snippet לבין טענה שאומתה מתוכן הדף. כך נסגור את הפער הבסיסי מול Tavily/Perplexity בלי להתחיל מ־API של מודל חיפוש. [3][15] | `חינם-אפשרי` לסינתזה מקומית; תשובת ספק מחייבת מפתח. |
| 2 | **מסנני חיפוש מפורשים** | לחשוף `allowed/denied domains`, זמן, שפה, סוג/קטגוריה ו־depth. `search_filters.py` כבר תומך בחלק מהמסננים מקומית; post-filter בחינם מוריד תוצאות אך לא משפר recall. העברת המסננים למנוע upstream דורשת תמיכת ספק או SearXNG מוגדר. [1][3][13] | `חינם-אפשרי` לסינון מקומי; `חינם-מוגבל` דרך SearXNG self-host; ספק keyed לשיפור recall. |
| 3 | **חיפוש אנכי שמיש דרך ה־plugin** | לחשוף את עזרי News/Images/Scholar שכבר קיימים ב־`free_verticals.py` כ־routes עם schema אחיד ומקור תוצאה ברור; לא להסתפק ב־`site:` על חיפוש כללי. לספקי API יש גם אינדקסים/מקורות אנכיים ייעודיים. [7][9] | `חינם-אפשרי` חלקית דרך קוד/מנועים חינמיים; כיסוי אנכי איכותי תלוי במקורות. |
| 4 | **חילוץ דינמי וסריקת אתר רחבה** | לחבר extraction של JS/PDF, מיפוי URL, crawl מוגבל ו־structured output; לאחד את `TavilyClient`/`FirecrawlClient` שכבר קיימים עם ה־URL gate, ולהחזיר כשלים לכל URL. GOAT יכול להציג JS לדף בודד, אך לא מספק כרגע שירות crawl/render מאוחד. [4][5][6][8] | `חינם-אפשרי` לדף יחיד/פתרון מקומי מוגבל; `דורש מפתח/תשלום` ל־crawl אמין, structured extraction ו־webhooks. |
| 5 | **מקורות חיפוש עצמאיים, כולל Reader** | להוסיף בחירה או fan-out מפורש ל־Jina Search/Reader ול־Marginalia, לצד SearXNG שכבר קיים. Jina נותן SERP עם תוכן הדפים, Marginalia נותן כיסוי שונה של אתרים קטנים/לא־מסחריים; אלה תורמים גיוון, לא תחליף לספק הקנוני. [16][17][18] | `חינם-מוגבל`: Jina ללא מפתח זמין במכסה מוגבלת; Marginalia מציע מפתח ציבורי שנחסם/מוגבל תדיר. |
| 6 | **נתיב אופציונלי ל־Brave כמדד עצמאי** | לאפשר בחירה מפורשת ב־Brave עבור אינדקס עצמאי, תוצאות News/Images/Videos/Places, ו־LLM Context מוכן ל־grounding; אפשר להוסיף Goggles לשליטה ב־rerank/filter. להשאיר אותו opt-in, לא fallback שקט ולא ברירת מחדל free-first. [9][10][22] | `דורש מפתח/תוכנית API`; תיעוד ההתחלה דורש הפעלת תוכנית ותשלום, ולכן לא לבנות עליו כנתיב חינמי. [11] |

## פערים לפי ספק

| ספק | 2–4 יכולות ש־GOAT אינו חושף כרגע | היתכנות חינמית |
|---|---|---|
| **Exa** | • חיפוש סמנטי/מצבי `auto` לצד קטגוריות ומסנני דומיין — בממשק GOAT אין כיום פרמטרי ספק כאלה. [1]<br>• חיפוש שמחזיר יחד תוכן LLM-ready: highlights, טקסט, summary, subpages וקישורים; GOAT מפריד חיפוש מחילוץ, וה־adapter המקומי אינו מחובר לכלי הציבורי. [1][2] | `דורש מפתח` לשימוש ב־Exa; חלק מהפילטרים/סינתזה אפשריים מקומית, אך אינם שקולים לאינדקס ולחילוץ של Exa. |
| **Tavily** | • פרמטרי עומק/נושא/טווח זמן/דומיינים, וכן אפשרות לצרף answer, raw content ותמונות; ה־API מציע את כולם, אך GOAT אינו חושף schema ציבורי תואם. [3]<br>• Extract בעד 20 URLs בבקשה, Crawl ו־Map מבוססי graph; extract batch ו־crawl כבר ממומשים ב־adapter המקומי אך לא מחוברים, ו־Map אינו route ציבורי. [4][5][6] | `דורש מפתח` ל־API; סינון מקומי/פיצול ידני אפשריים בחינם אך לא מספקים crawl/map שקול. |
| **Firecrawl** | • Search+scrape בקריאה אחת, עם תוצאות web/news/images ותוכן markdown/HTML/links/screenshots או highlights. [7]<br>• JS-aware scrape/crawl/map, פעולות דפדפן כמו click/fill/scroll, ו־JSON מובנה; ב־GOAT הכלי הציבורי מוגבל יותר, בעוד ה־adapter הקיים מכסה רק חלק מהמסלול. [8] | `דורש מפתח` ליכולות Firecrawl; render לדף בודד אפשרי דרך browser מקומי, אך crawl/structured extraction מלאים אינם חינמיים בהכרח. |
| **Brave Search API** | • אינדקס עצמאי ו־endpoints ייעודיים ל־Web, News, Images, Videos ו־Places; GOAT אינו מנתב כרגע ל־Brave. [9]<br>• LLM Context עם תוכן מוכן ל־grounding וכן Goggles/extra snippets/metadata להעשרת או שינוי דירוג; אין חוזה ציבורי מקביל ב־GOAT. [10][22] | `דורש מפתח/תוכנית API`; לא לסווג כ־free רק כי פתיחת חשבון אינה כרוכה בתשלום. [11] |
| **Bing Web Search** | • אין פער parity בר־מימוש מול Bing Web Search API הישן: Microsoft השביתה את Bing Search APIs ב־11 באוגוסט 2025, כולל הרשמה חדשה. [12]<br>• מסלול ההמשך שמיקרוסופט מציעה הוא Grounding with Bing Search בתוך Azure AI Agents, לא endpoint ציבורי חלופי ל־GOAT. אין להוסיף adapter ישיר ל־API שפרש; לבחון Azure integration רק אם יש דרישה עסקית נפרדת. [12] | API ישן: `לא-יעד/לא זמין`; Grounding ב־Azure: `דורש מפתח/תשתית Azure`. |
| **Perplexity Sonar API** | • תשובה שנוצרת על בסיס חיפוש ומלווה במקורות/תוצאות חיפוש; `goat_answer` המקומי מכסה רק סינתזה בסיסית, לא את מודל Sonar או את מחקר הספק. [15]<br>• מסנני domain/URL, תאריך פרסום/עדכון ו־recency עד 20 domains — לא קיימים כיום ב־schema הציבורי של GOAT. [13]<br>• `sonar-deep-research` ו־streaming של תשובה/metadata — אין מסלול multi-step research או streaming ייעודי ב־GOAT. [14][15] | `דורש מפתח` לשימוש ב־Sonar; תשובה מצוטטת בסיסית אפשר לממש בחינם מקומית. Deep Research הוא פער יקר יותר, לא MVP free-first. |
| **Marginalia ו־public search engines** | • אינדקס Marginalia מכוון לאתרי web קטנים/ישנים/לא־מסחריים — גיוון אינדקס שאינו מתקבל מה־DDG/Wikipedia/SearXNG שמוגדרים ב־GOAT. [17]<br>• API ציבורי עם מפתח `public` מאפשר ניסוי, אך מוגבל בקצב ואינו מאפשר custom filters; אין ל־GOAT connector ישיר או מדיניות quota עבורו. [16]<br>• SearXNG קיים, אבל המימוש המקומי מעביר רק query ו־format — אין כרגע בחירת engines/categories/time-range לכל קריאה. זהו פער חשיפה/ניתוב ולא פער בעצם קיום metasearch. | Marginalia: `חינם-מוגבל` לניסוי, לא לבסס עליו production. SearXNG: `חינם-אפשרי` אם self-host, עם עלות תפעול והגדרות מנועים. |
| **Jina AI Reader/Search** | • `r.jina.ai` ממיר URL לתוכן נקי ו־LLM-friendly — נתיב reader אחיד נוסף ל־`goat_extract`. [18]<br>• `s.jina.ai` מחזיר SERP של עד חמש תוצאות עם URL ותוכן הדפים באותה תשובה — קיצור דרך search+read שאינו חשוף ב־GOAT. [18] | `חינם-מוגבל`: אפשר להשתמש בלי מפתח; Jina מציינת שמפתח API מעלה את rate limit. לא להניח מכסה מספקת לפרודקשן. [18] |
| **Hermes Browser Extension (abundantbeing)** | • הרחבה צדדית ל־Chrome/Edge מחברת שיחה להקשר דפדפן, עם בחירת הקשר ו־drafting; GOAT כ־search plugin אינו מספק side panel או context handoff. [19][21]<br>• repo/release מתעדים browser control אופציונלי, scopes לטאבים, approvals מפורשים וגבולות פעולה; אלו אינם חלק מה־GOAT tools. [20]<br>• היסטוריית releases כוללת AI Tab Triage לארגון טאבים וגילוי כפילויות. זה פער UI/זרימת עבודה, לא מנוע חיפוש. [23] | `חינם-אפשרי` כ־integration עם ההרחבה הקיימת; עדיף לחבר את ה־GOAT tools דרך Gateway מאושר ולא לבנות שליטת דפדפן כפולה. חובה לשמר scopes, אישורי משתמש ו־readback. |

## מסקנות

- סדר free-first: לרשום `goat_answer`, לחשוף filters ו־verticals שכבר קיימים, ואז לחבר crawl/extract עם מגבלות URL וקריאות מפורשות לספקים keyed. מענה מצוטט, מסנני דומיין/זמן וחיפוש אנכי הם יכולות מתועדות אצל Tavily ו־Perplexity, ומנועי חיפוש מציעים verticals ייעודיים. [3][9][13][15]
- Jina/Marginalia הם ניסויי גיוון בעלות כניסה נמוכה יחסית, אך מכסות ציבוריות אינן בסיס מובטח לשירות. [16][18] Brave/Exa/Tavily/Firecrawl/Perplexity צריכים להישאר נתיבי opt-in הדורשים credential משלהם; אין fallback שקט ביניהם. [1][3][9][11][15]
- Bing Search API הישן אינו יעד לאחר הפרישה; Microsoft ממליצה על Grounding בתוך Azure AI Agents. [12] הרחבת ה־Browser Extension היא חיבור מוצרי נפרד; היכולת קיימת בפרויקט אחות ולכן לא לספור אותה כפיתוח מנוע חיפוש חדש. [19][20][23]

## מקורות מקומיים — baseline של GOAT

- `roadmap-gaps.md` — ארבעת הכלים הציבוריים והעובדה שה־adapters אינם מחוברים.
- `feature-gaps.md`, `search_filters.py`, `free_verticals.py`, `answer_synth.py`, `exa_adapter.py`, `tavily_adapter.py`, `firecrawl_adapter.py`, `browser_tier.py` — היכולות שכבר קיימות בקוד והפער בין helpers לבין API ציבורי.

## Sources

[1] https://exa.ai/docs/reference/search
[2] https://exa.ai/docs/reference/contents-api-guide-for-coding-agents
[3] https://docs.tavily.com/documentation/api-reference/endpoint/search
[4] https://docs.tavily.com/documentation/api-reference/endpoint/extract
[5] https://docs.tavily.com/documentation/api-reference/endpoint/crawl
[6] https://docs.tavily.com/documentation/api-reference/endpoint/map
[7] https://docs.firecrawl.dev/features/search
[8] https://docs.firecrawl.dev/advanced-scraping-guide
[9] https://api-dashboard.search.brave.com/documentation
[10] https://api-dashboard.search.brave.com/documentation/services/llm-context
[11] https://api-dashboard.search.brave.com/documentation/quickstart
[12] https://learn.microsoft.com/en-us/lifecycle/announcements/bing-search-api-retirement
[13] https://docs.perplexity.ai/docs/sonar/filters
[14] https://docs.perplexity.ai/docs/sonar/models/sonar-deep-research
[15] https://docs.perplexity.ai/docs/sonar/features
[16] https://about.marginalia-search.com/article/api
[17] https://www.marginalia.nu/marginalia-search
[18] https://jina.ai/reader
[19] https://github.com/abundantbeing/hermes-browser-extension/blob/main/README.md
[20] https://github.com/abundantbeing/hermes-browser-extension/releases/tag/v0.3.0
[21] https://github.com/abundantbeing/hermes-browser-extension/blob/main/CHANGELOG.md
[22] https://brave.com/search/api
[23] https://github.com/abundantbeing/hermes-browser-extension/releases
