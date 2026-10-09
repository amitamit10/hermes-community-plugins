# GOAT — מפת עבודה שנותרה (Top 8)

**מצב כללי: HOLD ללייב ולהפצה ציבורית.** יש התקדמות ממשית בקוד ובבדיקות, אבל אין GOAT פעיל בפרופיל, ההחלטה על ספק חיפוש קנוני אינה מיושמת באופן עקבי, והבדיקה העצמאית הסופית של מועמד ההפצה עדיין חסרה.

## תמונת מצב שנצפתה

- **לייב:** `hermes skills list` מחזיר 247 פעילים ו־0 מושבתים: 53 builtin, 178 local, 16 hub-installed. אין `goat` ברשימת הסקילים. `hermes plugins list --json` מחזיר 62 plugins (56 enabled, 6 not enabled), ללא GOAT; תיקיות GOAT אינן מותקנות תחת `/opt/data/skills` או `/opt/data/plugins`. `donsetch_hardened` נשאר MCP יחיד ומושבת.
- **קוד ובדיקות:** [gate-reverify-tick2.md](gate-reverify-tick2.md) מתעד 61 בדיקות staging, ‏4 ultimate, ‏160 packs ו־4,288 מקרי fuzz — כולם עברו. [OUTCOME_LEDGER.md](../../goat-public/goat-web/OUTCOME_LEDGER.md) אומר שתיקוני B1–B4 נחתו, אך ה־re-audit הסופי עדיין ממתין ו־export candidate ישן. מנגד, [reaudit2.md](reaudit2.md) עדיין מציג NO-GO עם חסמים שכבר דווח שתוקנו. לכן הראיות אינן מסונכרנות; אלה תוצאות מתועדות, לא הרצה מחדש במסגרת המיפוי הזה.
- **SearXNG:** יש מחקר ולקוח בקוד, אך לא נמצאה הוכחת התקנה. בדיקת Docker נכשלה בהרשאת socket; `127.0.0.1:8080` פתוח אך בעל התהליך לא זוהה, ולכן אין לייחס אותו ל־SearXNG. לקוח `free_stack` מציין ברירת מחדל `localhost:8888`, בעוד תיעוד ההתקנה מתאר Compose ב־8080.
- **Public:** checkout מקומי נקי על `main`, commit אחרון `v2.1`, ללא tags. ה־ledger עדיין מסמן public push כחסום. ה־README הציבורי מציג ספירות ישנות (56/96) לעומת gate report עדכני יותר (61/160). לא נמצאה ראיה לשחרור v3.

## Top 8 — לפי סדר עדיפות

### 1. P0 — להשלים re-audit סופי על מועמד אחד וקפוא

- **מה נשאר:** לאחד את הסתירה בין NO-GO הישן ב־`reaudit2.md` לבין ה־ledger וה־gates המאוחרים יותר. אין לאשר live או release על סמך בדיקות שעברו בלבד.
- **ראיות:** [reaudit2.md](reaudit2.md), [gate-reverify-tick2.md](gate-reverify-tick2.md), [OUTCOME_LEDGER.md](../../goat-public/goat-web/OUTCOME_LEDGER.md). ה־ledger מציין גם שה־export candidate stale.
- **סיום כש:** נבחר commit/hash יחיד; מבוצע re-audit בלתי תלוי של אותו עץ בדיוק; מעודכנים/מוחלפים ממצאי B1–B4; כל test suites, fuzz, staging audit ו־`hermes plugins validate` רצים מחדש על אותו מועמד; אין ממצא blocker פתוח.

### 2. P1 — להכריע וליישר ספק חיפוש קנוני ושרשרת fallback

- **מה נשאר:** המסמכים קובעים AnySearch אנונימי כקנוני ([search-fallback-chain.md](search-fallback-chain.md)); ה־registry עדיין קובע `goat_search`; מימוש `goat_search` ב־plugin משתמש ב־DDG כברירת מחדל; `free_stack.fallback_chain` מסודר SearXNG → Wikipedia → DDG. מכניקת fallback מפורשת כבר קיימת: כבויה כברירת מחדל ו־`MISSING_CONFIG` עוצר — אבל זו אינה אותה מדיניות ספקים כמו במסמך.
- **סיום כש:** יש החלטה אחת על canonical provider ועל fallback מותר; ה־registry, הכלים והמסמכים מתארים אותו סדר; כל מעבר מדווח עם מקור וסיבה; אין fallback אחרי `MISSING_CONFIG` או מעבר שקט לספק אחר; בדיקות מכסות כשל, מכסה, חוסר מפתח ו־no-results.
- **תלות:** לפני registry v2 וחיבור ספקים לכלים.

### 3. P1 — לממש registry v2, לא להסתפק בהערות

- **מה נשאר:** [registry-v2-notes.md](registry-v2-notes.md) הוא מפרט בלבד. ה־registry הקיים עדיין `schema_version: 1`, מגדיר capability classes בלבד ואין בו רשומות `providers`.
- **סיום כש:** מתווספות רשומות ספקים וסיווגים; AnySearch מוגדר `canonical-free` רק אם אושר במשימה 2; paid routes מצהירים `requires_key: true` ו־`MISSING_CONFIG` ללא fallback; Donsetch נשאר unavailable/future; Serper נשאר חסום עד אימות. מעודכנים schema, counts ובדיקות ולידציה.
- **מקור:** [ה־registry הנוכחי](../goat-ultimate/registry/capabilities.json), [הערות v2](registry-v2-notes.md).

### 4. P1 — לחשוף adapters ככלי Hermes אמיתיים

- **מה נשאר:** ה־plugin הקיים מפרסם ארבעה כלים בלבד: `goat_search`, `goat_extract`, `goat_crawl`, `goat_probe`. ה־provider clients ב־`adapters/` אינם מיובאים/מחוברים ל־plugin; `answer_synth` ו־`free_verticals` כוללים helpers של `register()`, אך גם הם אינם רשומים ב־plugin. לכן קיום adapter או unit tests אינו אומר שהוא כלי זמין למודל.
- **סיום כש:** נבחר scope מצומצם של כלים, מוגדרים schemas קשיחים ו־handlers; בחירת ספק ומפתחות נשארים בצד השרת; פלטים כוללים מקור/transition; fake-transport tests מכסים הצלחה, שגיאות ו־MISSING_CONFIG; `hermes plugins validate` מאשר את הרישום. `goat_answer` עם citations ומסננים מובנים הם מועמדי ההרחבה הראשונים מתוך [feature-gaps.md](feature-gaps.md), לא תנאי לכתיבה מחדש של clients.
- **מצב חלקי:** manifest `plugin.yaml` ורישום ארבעת הכלים קיימים ב־[ה־plugin הציבורי](../../goat-public/goat-web/plugins/goat-web/plugin.yaml); זה לא כולל את adapters ואינו מוכיח התקנה בלייב.

### 5. P1 — להתקין או לזהות ולאמת SearXNG במופע המיועד

- **מה נשאר:** [searxng-selfhost.md](searxng-selfhost.md) ו־[selfhost-matrix.md](selfhost-matrix.md) מתעדים מחקר והמלצה, לא instance פעיל. מצב ה־8080 המקומי אינו מזוהה, והרשאת Docker לא מאפשרת בדיקת containers.
- **סיום כש:** בעל השירות וה־host מאומתים; אם אין instance — מתקינים במופע מאושר עם JSON מופעל, endpoint/limiter מוגדרים ו־health check; אם כבר קיים — מאמתים זאת במקום התקנה כפולה. מיישרים את 8080/8888 מול `SearXNG_URL`; לא חושפים instance לציבור כברירת מחדל, ולא עוקפים CAPTCHA/rate limits. דרישת RAM של כ־2 GB במסמך היא הערכה, לא מפרט רשמי.

### 6. P1 — להפוך את חבילת ההתקנה ואת baseline של 247 לסגורים וניידים

- **מה נשאר:** ה־live count אומת כ־247; `skill-coverage.json` מכיל 247 assignments (74 mapped, 173 unmapped), אך מצביע גם על `../goat-ultimate/registry/live-inventory.json` שאינו קיים. בנוסף, ה־skill מצפה ל־`registry/capabilities.json` יחסית לתיקייתו בעוד ה־registry יושב כרגע כאח, וה־plugin נקרא בתיקייה `goat-web` אך manifest מצהיר `hermes-goat-web`.
- **סיום כש:** baseline מאושר של 247 נשמר בצורה מצומצמת/ניתנת לשחזור או מוסר אליו reference שבור; הנתיב היחסי ל־registry עובד לאחר התקנה; plugin ID אחיד בין שם תיקייה, manifest ופקודות; manifest/hash של הקיים מאפשרים לוודא שלא נדרס skill/plugin אחר.
- **מקורות:** [inventory-delta.md](inventory-delta.md), [skill-coverage.json](skill-coverage.json), [install-rehearsal.md](install-rehearsal.md).

### 7. P1 — לבצע התקנה מדורגת והפעלה בלייב, עם readback

- **מה נשאר:** לא נמצא GOAT בלייב; זו נקודת ההתחלה הנוכחית, לא אינדיקציה שהתקנה נכשלה. יש לבצע רק אחרי משימות 1–6 ובהרשאה מפורשת.
- **סיום כש:** מקפיאים שוב baseline של skills/plugins/MCP; מתקינים רק שני skills ו־plugin מדויק, תחילה disabled, ללא `--force` או bulk update; קוראים חזרה את ה־manifest, ארבעת הכלים, ה־registry וה־skills; מפעילים בנפרד רק לאחר אישור; בודקים session חדש. לפי baseline נוכחי, הציפייה היא 249 skills ו־63 plugins: לפני enable ‏56 enabled/7 not enabled, ואחריו 57/6; MCP נשאר ללא שינוי והמופע הקיים של `donsetch_hardened` נשאר disabled. אין restart ל־gateway במסגרת שלב זה.
- **מקור:** סדר ההתקנה וה־rollback ב־[install-rehearsal.md](install-rehearsal.md).

### 8. P2 — להכין ולפרסם v3 רק אחרי שערי ההפצה

- **מה נשאר:** מצב המאגר הציבורי שנצפה הוא v2.1, אין tag v3, וה־ledger עדיין מסמן public push כחסום. README/ספירות וחלק מהראיות ישנים; ב־`plugin.yaml` גרסת ה־plugin היא 0.1.0, ולכן יש ליישב versioning לפני release. פרסום דורש אישור אנושי מפורש.
- **סיום כש:** נבנה מחדש export candidate מה־hash שעבר את משימה 1; README, ספירות בדיקות, provenance, SECURITY/contact וגרסאות תואמים; נסגרו רישיונות ו־review ציבורי; מתקבל אישור מפורש; רק אז יוצרים tag/release v3 ודוחפים. אין לפרש checkout מקומי או README כראיית פרסום.
- **מקורות:** [README הציבורי](../../goat-public/README.md), [OUTCOME_LEDGER.md](../../goat-public/goat-web/OUTCOME_LEDGER.md), [install-rehearsal.md](install-rehearsal.md).

## סדר תלות קצר

`1 → 2 → 3 → 4`; משימה 5 מתבצעת אחרי החלטת route ממשימה 2; משימה 6 סוגרת את חבילת ההתקנה; משימה 7 רק אחרי כל שערי ה־live; משימה 8 היא מסלול פרסום נפרד שמותנה ב־1 ובאישור אנושי. אין לבצע התקנה, הפעלה או push במסגרת מפת העבודה הזו.
