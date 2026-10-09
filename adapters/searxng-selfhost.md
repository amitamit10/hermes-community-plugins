# SearXNG כ-backend חיפוש self-hosted

**תאריך בדיקה:** 2026-10-09. תיעוד upstream שנצפה מציג build ‏2026.10.7.[1]

## מסקנה / GOAT

| שדה | ערך | הערה |
|---|---|---|
| `requires_selfhost` | `true` | לשימוש אמין יש להפעיל ולתחזק instance משלכם. יש instances ציבוריים, אבל הם עשויים להשבית JSON ולסבול מחסימות upstream.[1][5] |
| התאמה ל-VPS עם 2 vCPU | **כן, לשימוש עצמי/תעבורה נמוכה** | הערכת תכנון, לא benchmark רשמי. דרישת RAM רשמית לא מפורסמת; ראו להלן.[5][11] |
| SPDX בקובצי המקור | `AGPL-3.0-or-later` | זהו מזהה ה-SPDX שמופיע בכותרות קוד בפרויקט. ה-README/מטא-נתוני GitHub מציגים `AGPL-3.0`, וקובץ `LICENSE` הוא נוסח AGPL גרסה 3; שמרו את ההבדל הזה בבדיקת רישוי/‏SBOM.[2][3][4] |

**המלצה מעשית:** 2 vCPU צפויים להספיק ל-instance פרטי עם מעט משתמשים. הייתי מקצה **כ-2 GB RAM** כדי להשאיר מרווח ל-SearXNG, Valkey ו-proxy; המספר הזה הוא **[לא-מאומת]** כהמלצת sizing, לא דרישת פרויקט. ה-VPS המדויק לא ניתן לאישור בלי לדעת RAM, עומס ומספר בקשות מקביליות. בתשובת GitHub יחידה, משתתף בפרויקט דיווח שהוא מריץ SearXNG על כמה מכונות 1 vCPU/512 MB ללא בעיות מהירות; זו אנקדוטה, לא מפרט או התחייבות רשמיים.[11]

## JSON API

ה-API הרשמי תומך ב-`GET` וב-`POST` בנתיבים `/` וגם `/search`. ב-GET הפרמטרים הם query string; ב-POST הם נשלחים כטופס `application/x-www-form-urlencoded`.[1]

```text
GET  /search?q=searxng&format=json
POST /search   body: q=searxng&format=json
```

כדי לקבל JSON צריך `format=json`, וב-settings של ה-instance להוסיף `json` תחת `search.formats`. אם הפורמט לא מופעל, התיעוד מציין תשובת `403 Forbidden`; ברירת המחדל המתועדת כוללת `html` בלבד, ו-instances ציבוריים רבים משביתים פורמטים נוספים.[1][6]

| פרמטר מתועד | משמעות / ערכים |
|---|---|
| `q` | חובה; מחרוזת החיפוש. תחביר חיפוש של מנוע מסוים עשוי לעבוד רק במנועים שתומכים בו. |
| `categories` | קטגוריות פעילות, מופרדות בפסיקים. |
| `language` | קוד שפה; ברירת המחדל נקבעת ב-settings. |
| `pageno` | מספר עמוד, ברירת מחדל `1`. |
| `time_range` | `day`,‏ `month`,‏ `year`; רק במנועים שתומכים בכך. |
| `format` | `json`,‏ `csv`,‏ `rss`; חייב להיות מופעל ב-`search.formats`. |
| `safesearch` | `0`,‏ `1`,‏ `2`; ברירת המחדל מה-settings, והסינון תלוי בתמיכת המנוע. |
| `theme` | ברירת מחדל `simple`; האפשרויות תלויות ב-instance. |

זו רשימת הפרמטרים בדף ה-API הרשמי הנוכחי. `engines` אינו מופיע שם, לכן לא להסתמך עליו כפרמטר API מתועד בלי לבדוק מול הגרסה המותקנת.[1]

## משאבים ו-Docker

- מסמכי ההתקנה הרשמיים דורשים Docker או Podman וממליצים על התקנה באמצעות Compose; הם **לא מפרטים דרישת מינימום רשמית ל-CPU או RAM**.[5]
- ב-Compose המתועד מוצגים שירות SearXNG ושירות Valkey. Valkey נדרש אם מפעילים את ה-limiter; כשחושפים instance לציבור, התיעוד ממליץ גם על reverse proxy.[5][8]
- `image_proxy` הוא אופציונלי וההגדרה משתמשת בזיכרון נוסף.[10]
- מסקנת 2 vCPU לעיל היא sizing משוער לשימוש אישי/דל-נפח בלבד. אין כאן הבטחה לביצועים בעומס, ואין מפרט RAM רשמי שאפשר לאמת.[5][11]

## מגבלות, rate limits ו-CAPTCHAs

**מנועי upstream:** אין מכסה אחידה שמובטחת לכל המנועים; כל שירות חיצוני קובע מדיניות משלו. SearXNG מתעד תגובות כגון CAPTCHA, חסימת גישה ו-HTTP `429`, ומשהה מנועים שנכשלו כברירת מחדל: CAPTCHA — ‏24 שעות; Access denied — ‏24 שעות; Too many requests — ‏3600 שניות לפי settings (כ-שעה). דף ה-exceptions מתאר את ברירת המחדל האחרונה כ-3660 שניות, ולכן יש פער של דקה בין שני דפי התיעוד; לבדוק את `settings.yml` של הגרסה שרצה.[6][7] אלה זמני השהיה פנימיים של SearXNG, **לא** מכסות בקשות שמובטח שה-upstream יתיר.

CAPTCHA או חסימת IP של שרת ה-SearXNG עדיין עלולות לקרות; ה-limiter המקומי מיועד לצמצם תעבורת bot שנכנסת ל-instance, לא לעקוף מדיניות של מנועי החיפוש.[8] התיעוד מתאר פתרון ידני אפשרי דרך SSH/SOCKS, כך שדפדפן יגלוש דרך כתובת ה-IP של השרת ויפתור את ה-CAPTCHA באתר החיצוני; אין בכך הבטחה שהחסימה לא תחזור.[12]

**Rate limit של ה-instance עצמו (נפרד מה-upstream):** ברירת המחדל המתועדת של `server.limiter` היא `false`; אם מפעילים אותו, נדרש Valkey. ב-IP limiter, בקשות API שאינן `format=html` מוגבלות כברירת מחדל ל-4 בקשות לשעה לכל IP. לכן יש לבדוק/להתאים את מגבלת ה-API לפני חיבור אוטומציה שמבצעת הרבה קריאות; זו מגבלה נכנסת של ה-instance, לא של מנוע חיצוני.[9][10]

## Sources

[1] https://docs.searxng.org/dev/search_api.html
[2] https://github.com/searxng/searxng
[3] https://github.com/searxng/searxng/blob/master/LICENSE
[4] https://github.com/searxng/searxng/blob/master/searx/settings_loader.py
[5] https://docs.searxng.org/admin/installation-docker.html
[6] https://docs.searxng.org/admin/settings/settings_search.html
[7] https://docs.searxng.org/src/searx.exceptions.html
[8] https://docs.searxng.org/admin/searx.limiter.html
[9] https://docs.searxng.org/src/searx.botdetection.html
[10] https://docs.searxng.org/admin/settings/settings_server.html
[11] https://github.com/searxng/searxng/discussions/3884
[12] https://docs.searxng.org/admin/answer-captcha.html
