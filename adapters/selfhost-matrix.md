# מטריצת חיפוש self-host / free-first

**איך לקרוא את הציונים:** קושי Docker/self-host הוא הערכה תפעולית מ־1 (קל ביותר) עד 5 (קשה ביותר), כולל הבאת החיפוש לשימוש מועיל ולא רק הפעלת קונטיינר. איכות API היא הערכה איכותנית של תיעוד, פורמט מובנה וקלות אינטגרציה — לא ציון לרלוונטיות התוצאות.

| אפשרות | רישיון | קושי Docker / self-host (1–5) | איכות API | שימוש אנונימי ללא מפתח | פסק דין ל־GOAT free-first stack |
|---|---|---|---|---|---|
| **SearXNG** | AGPL-3.0-or-later.[5] | **3/5** — התקנת Compose מומלצת ומתועדת; הפעלה ציבורית אמינה דורשת הגדרות, proxy והקשחה.[3] | **גבוהה** — GET/POST פשוטים ו־JSON/CSV/RSS; פורמט JSON חייב להיות מופעל במופע, ורבים מהמופעים הציבוריים מכבים אותו.[1] | **כן** — אפשר לחפש במופע שלך בלי מפתח לספק חיפוש; גישה אנונימית ו־JSON תלויות בהגדרות המפעיל.[1][3] | **בחירה ראשית** לחיפוש כללי בחינם ובשליטתך. תוצאות ותקלות תלויות במנועי המקור שמוגדרים.[1][2] |
| **Whoogle** | MIT.[39] | **1/5 להתקנה** — הרצת Docker פשוטה, אבל קלות ההתקנה אינה משנה את מצב השירות הנוכחי.[38] | **לא שמיש בפועל** — בעבר תמך ב־JSON, אך הודעת הפרויקט העדכנית אומרת שהוא כבר לא מחזיר תוצאות ושאין עוד פיתוח/תחזוקה.[38] | **לא, כיום** — המודל ההיסטורי היה חיפוש ללא מפתח, אך upstream מדווח שאין תוצאות; גם מסלול BYOK המתועד הוכרז כלא ישים.[38] | **להוציא מה-stack הפעיל**; לא לבנות עליו ולא להחשיבו כגיבוי, אלא אם fork מוכח עובד ומתוחזק.[38][39] |
| **YaCy** | GPL-2.0-or-later; יש רכיבים תחת LGPL.[8][9] | **4/5** — יש image רשמי להפעלה, אך חיפוש מועיל תלוי באינדקס, אחסון מתמשך, crawl והגדרות; ההקמה כבדה יותר מ־metasearch.[9][14] | **בינונית** — ממשקי HTTP עם JSON ו־XML זמינים, אך הם חלק מממשק YaCy ופחות אחידים מ־API כללי של metasearch.[8] | **כן** — אפשר להפעיל שרת חיפוש משלך בלי מפתח API מספק חיצוני; היקף ואיכות התוצאות תלויים באינדקס המקומי/ברשת.[8][14] | **תוספת נישתית** לחיפוש מקומי, ארגוני או אינדקס עצמאי; לא תחליף קל ל־SearXNG כחיפוש Web כללי.[9][14] |
| **SepiaSearch** | רישיון ה־search-index הוא AGPL-3.0; הפרויקט מתאר מנוע ואתר נפרדים, לכן יש לבדוק רישיון לכל רכיב UI בנפרד.[13][50] | **4/5 (הערכה)** — אפשר לארח רשימת מופעים, אינדקס ואתר חיפוש משלך, אך מדובר בהרכבת רכיבים ולא במנוע Web כללי מוכן.[13] | **טובה בתחום הצר** — API מובנה לחיפוש PeerTube ב־JSON, ללא מפתח API לפי מנוע SearXNG המשתמש בו; מוגבל לסרטונים/ערוצים/פלייליסטים של PeerTube.[12][36] | **כן, לתוכן PeerTube** — ה־API הציבורי אינו דורש מפתח לפי האינטגרציה המתועדת; אין בכך כיסוי לחיפוש Web כללי.[12][36] | **מחבר ייעודי בלבד** אם גילוי תוכן PeerTube חשוב; לא להכניס כספק החיפוש הראשי.[12][13] |
| **Wikipedia Action API** *(baseline)* | קוד MediaWiki/API: GPL-2.0-or-later; טקסט Wikipedia בדרך כלל CC BY-SA 4.0 וגם GFDL, בכפוף לחריגים/רישיון ספציפי לפריט.[18][43] | **1/5*** — אין מה לארח כדי להשתמש ב־API הציבורי של Wikimedia; זו נקודת ייחוס hosted, **לא** אפשרות self-host.[18] | **גבוהה לידע ויקיפדי** — Action API מתועד ומחזיר נתוני חיפוש מובְנים; הקריאה היא בסגנון `action=query&list=search`.[18][29] | **כן לקריאות בלבד** — חיפוש/קריאה זמינים בלי access token; פעולות שמשנות נתונים דורשות token.[29] | **להשאיר כ־fallback חינמי וללא מפתח** לשאלות אנציקלופדיות/איתור ערכים, לא כתחליף לאינדקס Web.[18][29][43] |

\* ב־Wikipedia: ציון הקושי מתאר שימוש ב־API hosted בלבד; אין כאן ציון אפשרות לפריסה עצמית. **המלצה קצרה:** SearXNG ראשי, Wikipedia כ־baseline משלים; YaCy ו־SepiaSearch רק לפי צורך מקומי/תחומי; Whoogle מחוץ לברירת המחדל כל עוד upstream אינו מחזיר תוצאות.

## Sources

[1] https://docs.searxng.org/dev/search_api
[2] https://docs.searxng.org
[3] https://docs.searxng.org/admin/installation-docker.html
[5] https://github.com/searxng/searxng
[8] https://github.com/searxng/searxng/blob/master/README.rst
[9] https://github.com/searxng/searxng/blob/master/docs/admin/installation-docker.rst
[12] https://sepiasearch.org
[13] https://framablog.org/2020/09/22/sepia-search-our-search-engine-to-promote-peertube
[14] https://yacy.net
[18] https://www.mediawiki.org/wiki/API:Search
[29] https://www.mediawiki.org/wiki/API:FAQ/en
[36] https://github.com/searxng/searxng/blob/b3e08f2a/searx/engines/sepiasearch.py
[38] https://github.com/benbusby/whoogle-search/blob/main/README.md
[39] https://github.com/benbusby/whoogle-search
[43] https://wikimediafoundation.org/what-we-do/wikimedia-projects/wikipedia
[50] https://framagit.org/framasoft/peertube/search-index/-/blob/master/LICENSE
