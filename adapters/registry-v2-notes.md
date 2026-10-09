# הערות למעבר capabilities.json ל-v2

הערות אלה מתעדות את שינויי הרישום המבוקשים; הן אינן עורכות את `capabilities.json`. ברישום הנוכחי `capabilities` מתאר בעיקר מחלקות יכולת, בעוד שסיווגי ספקים דורשים ייצוג מפורש. ב-v2 הוסיפו רשומות ספק נפרדות (או מבנה שקול) במקום לדחוס כמה ספקים לתוך `overlaps_resolved`.

## רשומות להוספה או לעדכון

| מזהה ספק | פעולה וסיווג ב-v2 | הערות ניתוב |
|---|---|---|
| `anysearch` | להוסיף/לעדכן כ-`canonical-free` עבור `web-search`; גישה אנונימית זמינה, מפתח אופציונלי | זהו ספק החיפוש החינמי הקנוני. `ANYSEARCH_API_KEY` משפר מכסה, אך אינו דרישת תצורה. עדכנו בהתאם את הקישור הקנוני של יכולת `web-search` במקום להשאיר את `goat_search` כקנוני יחיד, אם AnySearch הוא היעד הקנוני שנבחר. |
| `donsetch` | להוסיף/לעדכן כ-`future-unavailable` | לא זמין לניתוב; אין להציג כחלופה פעילה או fallback. |
| `tavily` | להוסיף/לעדכן כ-`route` עם `requires_key: true` | חסר מפתח עבור ספק שנבחר ⇒ `MISSING_CONFIG`, ללא בקשת ספק וללא fallback שקט. |
| `exa` | להוסיף/לעדכן כ-`route` עם `requires_key: true` | חסר מפתח עבור ספק שנבחר ⇒ `MISSING_CONFIG`, ללא בקשת ספק וללא fallback שקט. |
| `firecrawl` | להוסיף/לעדכן כ-`route` עם `requires_key: true` | חסר מפתח עבור ספק שנבחר ⇒ `MISSING_CONFIG`, ללא בקשת ספק וללא fallback שקט. |
| `serper` | להוסיף/לעדכן כ-`route` עם `requires_key: true` | סיווג דורש מפתח אינו אישור להפעיל endpoint: הביקורת מסמנת endpoint/auth כלא מאומתים. השאירו חסום תפעולית עד אימות תיעוד first-party. |

ארבעת ספקי ה-paid לעיל הם ספקי החיפוש המופיעים ברשומת ה-gate הקיימת (Firecrawl, Exa, Tavily, Serper); Browserbase stealth ו-Bright Data נשארים מחוץ לרביעיית חיפוש זו. `You.com` מופיע במסמך הביקורת, אך אינו ברשימת ה-gate הקיימת; אל תוסיפו אותו לרביעייה או למסלול fallback זה בלי החלטת scope ורשומה נפרדת. אין להשתמש בפרופיל MCP החינמי שלו כדי לעקוף מפתח חסר במתאם API keyed.

## אילוצי registry

- שמרו את שער paid הקיים: `requires_key: true`, `missing_config_error: "MISSING_CONFIG"`, `on_missing_config: "fail_closed_no_fallback"`; רצוי לשקף את הדרישה גם בכל רשומת ספק, כדי שלא להסתמך על ברירת מחדל גלובלית.
- הוספת רשומת ספק אינה הופכת אותה ל-canonical. רק `anysearch` הוא `canonical-free`; ספקי ה-paid הם `route` ודורשים בחירה מפורשת ומפתח משלהם.
- אל תסמנו את `serper` כמוכן לביצוע עד שה-endpoint ושיטת האימות יאומתו; המצב `route-requires_key` מתאר מדיניות גישה, לא אימות טכני.
- אם v2 משנה את מבנה הרשומות, עדכנו את `schema_version`, את ה-schema, ואת `counts` רק לאחר ספירה מחדש של הרשומות בפועל. אל תחשיבו רשומות ספק כרשומות מחלקת יכולת בלי שהספירה מוגדרת כך.
