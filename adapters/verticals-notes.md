# הערות: סקילים ורטיקליים מול goat-ultimate

## היקף ומקור הכרעה

המיפוי כולל את 8 הסקילים הוורטיקליים שנבדקו. שיוך המחלקות משקף את `goat-packs/skill-coverage.json`; `goat-ultimate/registry/capabilities.json` הוא רישום הניתוב הקנוני. הרישום הנוכחי כולל 11 מחלקות: 4 במצב `keep`, 7 במצב `route`, ו-0 במצב `future`. לא שונתה סמכות הרישום ולא הופעלו ספקים.

## חפיפות והכרעה קנונית

| מחלקת router | סקילים חופפים | נשאר canonical | גבול/הכרעה |
|---|---|---|---|
| `web-search` | `arxiv`, `competitor-news-monitor` | `goat_search` | אלה זרימות ייעודיות לאקדמיה ולמודיעין תחרותי. הן מספקות הנחיות/מקורות ויכולות להרכיב חיפוש ופידים, אך אינן מחליפות את ספק החיפוש הקנוני. |
| `rss` | `rss-feeds`, `blogwatcher` | `rss-feeds` | `rss-feeds` הוא מסלול הקריאה הקנוני. `blogwatcher` מוסיף סריקה מתמשכת, מסד מקומי ומצב read/unread; הוא תוסף stateful, לא יעד קנוני נוסף לאותה מחלקה. |
| `media` | `youtube-content` | `youtube-content` | הסקיל עצמו הוא ספק המדיה הקנוני ברישום. |
| `maps` | `maps` | `hermes-map-artifacts` | הקנוני ברישום הוא יצירת ארטיפקטים של מפות. סקיל `maps` מספק geocoding, POI, מסלולים ואזורי זמן, ולכן הוא שימוש גאוגרפי ייעודי ולא תחליף למסלול הארטיפקטים. |
| ללא התאמה | `polymarket`, `weather` | אין | אין מחלקת router ישירה ברישום הנוכחי; לא להסוותם כ-`web-search` או כ-`maps`. |

## Future — הצעות בלבד, לא נתיבים פעילים

- `polymarket`: אפשר לשקול מחלקה עתידית כגון `prediction-market-data` עבור נתוני שוק ציבוריים. היא אינה קיימת כרגע; אין canonical provider או dispatch עבורה.
- `weather`: אפשר לשקול מחלקה עתידית כגון `weather` עבור תחזיות. היא אינה קיימת כרגע; אין canonical provider או dispatch עבורה.
- `blogwatcher` ו-`competitor-news-monitor`: אם יוגדר בעתיד מוצר ניטור מתמשך עם מצב, cadence ו-delivery עצמאיים, אפשר להעריך מחלקות נפרדות ל-`feed-monitoring` או `company-monitoring`. כרגע להשתמש בהם כזרימות מתמחות סביב המחלקות הקיימות, בלי להוסיף ספק קנוני.

`unmapped` במפה פירושו שאין התאמה ישירה למחלקה קיימת, לא שהרישום כבר מסמן capability כ-`future`. לפי כללי `goat-ultimate`, capability עתידי לא ניתן ל-dispatch עד שרשומה מאושרת מופיעה במפורש ב-registry. כל 8 הסקילים מצהירים על גישה שאינה דורשת מפתח API; תלות ב-CLI או בספרייה (למשל `blogwatcher-cli` ו-`youtube-transcript-api`) אינה `requires_key`.

## ספירות

- סקילים: **8**; משויכים למחלקה קיימת: **6**; `unmapped`: **2**.
- לפי מחלקה: `web-search` 2, `rss` 2, `maps` 1, `media` 1, `unmapped` 2.
- `requires_key=true`: **0**; `requires_key=false`: **8**.
