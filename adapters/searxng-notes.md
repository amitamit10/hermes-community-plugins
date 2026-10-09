# SearXNG — מחקר קצר

**נבדק:** 2026-10-09, מול התיעוד הרשמי ו-README של המאגר.

## מה זה ורישיון

SearXNG הוא מנוע **metasearch** שמאגד תוצאות ממנועי חיפוש ושירותים אחרים; הפרויקט מתאר אותו ככזה שאינו עוקב אחר משתמשים ואינו בונה עליהם פרופילים. פרטיות בפועל עדיין תלויה במפעיל ה-instance שבו משתמשים, ולכן למי שרוצה שליטה בלוגים ובהגדרות מתאימה התקנה עצמית. [אודות SearXNG](https://docs.searxng.org/user/about.html) · [README במאגר](https://github.com/searxng/searxng/blob/master/README.rst) · [למה instance פרטי](https://docs.searxng.org/own-instance.html)

README של המאגר מציין **GNU Affero General Public License (AGPL-3.0)**; שורת ה-SPDX בראש ה-README מציינת `AGPL-3.0-or-later`. לעיון בתנאים המחייבים: [README](https://github.com/searxng/searxng/blob/master/README.rst) ו-[קובץ LICENSE](https://github.com/searxng/searxng/blob/master/LICENSE).

## התחלה מהירה ב-Docker

המסמכים הרשמיים ממליצים על התקנת Compose. נדרשת התקנת Docker פעילה; בתבנית הנוכחית SearXNG נחשף מקומית ב-`http://localhost:8080`. יש לערוך את `.env` ואת `core-config/settings.yml` לפי הצורך לפני חשיפה מחוץ למחשב. [הוראות ההתקנה ב-Docker](https://docs.searxng.org/admin/installation-docker.html)

```sh
mkdir -p ./searxng/core-config/
cd ./searxng/
curl -fsSL \
  -O https://raw.githubusercontent.com/searxng/searxng/master/container/docker-compose.yml \
  -O https://raw.githubusercontent.com/searxng/searxng/master/container/.env.example
cp -i .env.example .env
# לערוך את .env ולהגדיר ערכים מתאימים
# nano .env
docker compose up -d
# בדיקת השירותים והלוגים:
docker compose ps
docker compose logs -f core
```

לעצירה: `docker compose down`. לפני פרסום ה-instance באינטרנט יש להגדיר אותו כראוי ולהציב reverse proxy; אין להתייחס לברירות המחדל של התקנת בדיקה כאל הגדרת production. התבנית הרשמית כוללת שירות Valkey, שנדרש אם מפעילים את ה-limiter.

## API חיפוש בפורמט JSON

ה-API מקבל `GET` או `POST` בנתיבים `/` ו-`/search`. ב-GET הפרמטרים הם query string. כדי לקבל JSON יש לשלוח `format=json`; המנהל צריך לאפשר את הפורמט ב-`search.formats`, ואחרת השרת עשוי להחזיר `403 Forbidden`. התיעוד מזהיר שרבים מה-instances הציבוריים משביתים פורמטים שאינם HTML. [Search API](https://docs.searxng.org/dev/search_api.html)

דוגמת URL רשמית (החליפו את שם המארח ב-instance שלכם):

```text
https://searx.example.org/search?q=searxng&format=json
```

`q` הוא חובה. פרמטרים שימושיים נוספים כוללים `categories` (רשימה מופרדת בפסיקים), `language`, `pageno` (ברירת מחדל 1), `time_range` (`day`,‏ `month`,‏ `year`) ו-`safesearch` (`0`,‏ `1`,‏ `2`); התמיכה בחלק מהאפשרויות תלויה במנועים ובהגדרות ה-instance. [רשימת הפרמטרים הרשמית](https://docs.searxng.org/dev/search_api.html)

מבנה תגובת JSON הנוכחי כולל את המפתח `query` ורשימות `results`,‏ `answers`,‏ `corrections`,‏ `infoboxes`,‏ `suggestions` ו-`unresponsive_engines`. פרטי כל תוצאה משתנים לפי סוג התוצאה והמנוע, לכן יש להתייחס לשדות של פריט בודד כנתונים אופציונליים ולא כסכימה קשיחה. [מימוש יצירת תגובת JSON במאגר](https://github.com/searxng/searxng/blob/master/searx/webutils.py)

```json
{
  "query": "searxng",
  "results": [
    {"title": "...", "url": "https://...", "content": "...", "engine": "..."}
  ],
  "answers": [],
  "corrections": [],
  "infoboxes": [],
  "suggestions": [],
  "unresponsive_engines": []
}
```

## מגבלות ונימוסי שימוש

- אין להניח שכל instance ציבורי מאפשר API או JSON: בדקו את מדיניות המפעיל ואת זמינות `format=json` לפני שילוב לקוח. משתמשים ב-instance ציבורי צריכים גם לסמוך על המפעיל לגבי שמירת הבקשות. [Search API](https://docs.searxng.org/dev/search_api.html) · [מסמכי instance פרטי](https://docs.searxng.org/own-instance.html)
- מנגנון ה-limiter של SearXNG נועד לחסום תעבורת bot שעלולה לגרום למנועי החיפוש שמאחורי SearXNG להחזיר CAPTCHA או לחסום את כתובת ה-IP של השרת. לפי ברירות המחדל המתועדות, כאשר הגבלת ה-IP פעילה, בקשות API (פורמט שאינו `html`) מוגבלות ל-4 בקשות בכל חלון של שעה ל-IP; זהו **ערך ברירת מחדל של המימוש**, לא הבטחה או מכסה אחידה לכל instance. המפעיל יכול לשנות הגדרות או להשבית limiter. [Bot Detection — Rate limit](https://docs.searxng.org/src/searx.botdetection.html) · [Limiter](https://docs.searxng.org/admin/searx.limiter.html)
- ללקוח: העדיפו instance משלכם לשימוש תכוף/אוטומטי, שלחו בקשות מעטות ובהפרשים, השתמשו ב-User-Agent מזוהה ולא מתחזה לדפדפן, וכבדו תנאים מקומיים. אם מתקבל `429`, עצרו והמתינו במקום לבצע retries צפופים; אל תנסו לעקוף CAPTCHA או הגבלת גישה. שימוש יתר בשירות ציבורי עלול לפגוע בתוצאות של משתמשים אחרים עקב חסימות upstream. [Limiter](https://docs.searxng.org/admin/searx.limiter.html) · [השלכות של instance ציבורי](https://docs.searxng.org/own-instance.html)

## לקוח Python ללא תלויות (stdlib `urllib`)

```python
import json
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def search(instance: str, query: str) -> dict:
    params = urlencode({"q": query, "format": "json", "pageno": 1})
    url = f"{instance.rstrip('/')}/search?{params}"
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "my-search-client/1.0 (contact: admin@example.org)",
        },
    )
    try:
        with urlopen(request, timeout=15) as response:
            return json.load(response)
    except HTTPError as exc:
        if exc.code == 403:
            raise RuntimeError("JSON format may be disabled on this instance") from exc
        if exc.code == 429:
            raise RuntimeError("Rate limited; stop and wait before trying again") from exc
        raise


payload = search("http://localhost:8080", "SearXNG JSON API")
for result in payload.get("results", []):
    print(result.get("title", ""), result.get("url", ""))
```

הדוגמה מקודדת את הפרמטרים באמצעות `urlencode`, קוראת JSON ישירות מ-`urlopen`, ומטפלת במפורש ב-403 וב-429. אם משתמשים ב-instance ציבורי, יש להתאים את נפח הבקשות למדיניות המפעיל; הדוגמה אינה מנסה לעקוף הגנות.
