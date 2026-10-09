# דוח UX/DX — GOAT packs

בדיקת קריאה בלבד של מסמכי `goat-web`, `goat-ultimate`, manifest, דוגמאות, חזרת ההתקנה וה־README הציבורי. להלן ששת הפערים בעלי ההשפעה הגבוהה ביותר; ההצעות הן תיקוני תיעוד/אריזה, לא שינויים שבוצעו.

## 1. [P1] אין מסלול Quickstart או התקנה שאפשר להשלים בפחות מחמש דקות

ה־README הציבורי מציג פקודת `hermes plugins validate` בלבד, בלי דרישות מוקדמות, התקנה, enable, בדיקת smoke, או תוצאה צפויה (`README.md:13–22`). חזרת ההתקנה אומרת שאין כרגע מקור plugin בלתי־משתנה, ש־`hermes plugins install` אינו מקבל נתיב מקומי, וש־`hermes skills install` אינו מתקין מתיקייה מקומית (`scratch/goat-packs/install-rehearsal.md:30–36, 54–56`). לכן אין למשתמש חדש דרך מתועדת להגיע מכלום לכלי עובד. גם אין עמודת Troubleshooting שמסבירה מה לעשות כש־validate נכשל או כשמתקבלים `URL_BLOCKED`, `REDIRECT_BLOCKED` או `MISSING_CONFIG`.

**תיקון מוצע:** לאחר קיבוע שיטת הפצה נתמכת, להוסיף Quickstart קצר עם גרסת Hermes נתמכת, התקנה מהמקור/ה־ref המדויקים, enable, בדיקת כלי קריאה בלבד ופלט צפוי. להוסיף טבלת שגיאה → משמעות → בדיקה/פעולה. עד אז לסמן בבירור שאין מסלול התקנה מאושר, במקום להשאיר את הקורא להסיק פקודות.

## 2. [P1] קובץ ה־registry לא נמצא בתוך חבילת ה־skill שאליה הנתיב מצביע

`goat-ultimate` קובע ש־`registry/capabilities.json` הוא מפת הניתוב הקנונית (`goat-ultimate/skills/goat-ultimate/SKILL.md:8`), אבל בעץ המקור הקובץ נמצא ב־`goat-ultimate/registry/`, מחוץ לתיקיית ה־skill. חזרת ההתקנה מזהה זאת ומציעה להעתיקו אל `$HERMES_HOME/skills/goat-ultimate/registry/` (`scratch/goat-packs/install-rehearsal.md:34, 42–43`), אך ה־README לא מציין שהעתקה זו חובה. התקנת ה־skill לבדו משאירה את הקורא בלי המפה שעליה הוא מצווה להסתמך.

**תיקון מוצע:** לארוז את ה־registry כחלק מתיקיית ה־skill ולבדוק ש־`registry/capabilities.json` נפתר לאחר התקנה/פריסה של החבילה; לחלופין, לעדכן את ההפניה לנתיב זמין ולתעד במפורש את חובת ההעתקה.

## 3. [P2] טבלת הניתוב נותנת יעדים, אך לא כלל החלטה למשתמש

ה־skill דורש לבחור בדיוק `canonical_provider`, אך הטבלה רק ממפה שמות כלליים כמו `extraction`, `crawl` ו־`browser` (`goat-ultimate/skills/goat-ultimate/SKILL.md:8–24`). היא לא מבהירה מתי לקרוא דף יחיד לעומת לסרוק אתר, מתי חיפוש צריך להמשיך לחילוץ, או איך לנתב בקשת בדיקת נגישות. `goat_probe` מתועד ככלי קיים ב־`goat-web`, אך אינו מוזכר כלל במפת הניתוב. בנוסף, לא מצוין מה לעשות אם ה־plugin אינו מותקן/מופעל.

**תיקון מוצע:** להוסיף decision table עם דוגמאות קצרות: חיפוש בלבד → `goat_search`; קריאת URL יחיד → `goat_extract`; גילוי דפים באותו origin → `goat_crawl`; בדיקת reachability בלבד → `goat_probe` כפעולת עזר או לציין במפורש שאינו route עצמאי; אינטראקציה בדפדפן → `browser_exec`. לציין שהנתיב זמין רק כשה־plugin מותקן ומופעל, ומהו כשל־סגור כשהוא חסר.

## 4. [P1] דוגמאות הכלים אינן תואמות ל־schema ולפלט בפועל

הדוגמה הראשונה שולחת `limit` ל־`goat_search` (`goat-web/references/examples.md:7–14`), אך ה־schema דורש `max_results` (`goat-web/skills/goat-web/references/tool-schemas.md:5–16`); ה־plugin גם אוסר שדות נוספים (`plugins/goat-web/__init__.py:18–27, 78–86`). לכן הדוגמה אינה קריאה תקינה להעתקה. `adapters/examples2.md` מצהיר שהוא מדגים את צורת הפלט של `goat_tools.py`, אך מציג `ok`/`content` ו־`limit`, ובדוגמאות crawl אף טוען שאין פרמטר `max_pages` (`adapters/examples2.md:3–15, 34–53, 225–227`). אלה אינם חוזי הפלט/קלט של ה־plugin המתועד.

**תיקון מוצע:** לייצר את הדוגמאות מתוך ה־schemas/fixtures של `goat-web` ולוודא אותן מול ה־handlers. לסמן או להעביר בנפרד דוגמאות של adapters ניסיוניים, ולהבהיר שהן אינן קריאות ישירות לכלי הציבוריים.

## 5. [P1] חזרת ההתקנה מתארת עץ ישן ואינה תואמת לחבילה הציבורית שנבדקה

מסמך החזרה אומר שהבדיקות בוצעו מול `goat-browser-staging` ומסיק שחסרים `plugin.yaml` ו־`__init__.py` (`scratch/goat-packs/install-rehearsal.md:20, 26–35`). בעץ הציבורי שנבדק קיימים `goat-web/plugins/goat-web/plugin.yaml`, `__init__.py`, `goat_tools.py` ו־`url_gate.py`; גם ה־README הציבורי מפנה להרצת validate על תיקיית ה־plugin (`goat-web/README.md:12`, `goat-web/plugins/goat-web/`). לא ברור לקורא אם חסם ה־NO-GO עדיין נכון, לאיזה snapshot הוא חל, ואילו תקלות כבר תוקנו. עצם נוכחות הקבצים אינה מוכיחה שה־plugin עובר validate, אבל היא כן סותרת את טענת הקבצים החסרים.

**תיקון מוצע:** לציין בראש החזרה commit/ref ותאריך של העץ שנבדק; להריץ אותה מול אותו snapshot ציבורי, לעדכן את הממצאים, ולהפריד בין מצב ישן לבין חסמים שעדיין אומתו. לצרף תוצאות validate/doctor עדכניות ולא להציג מסקנות ישנות כאילו הן מצב החבילה הנוכחית.

## 6. [P2] שם החבילה ומצב האבטחה אינם עקביים בין דפי הכניסה

ה־README הציבורי מכנה את האוסף “security-reviewed” (`README.md:1–5`), בעוד README של `goat-web` אומר שלא הושלמה סקירה עצמאית ושאין אישור לשחרור (`goat-web/README.md:12–14`). במקביל, שם ה־plugin ב־manifest הוא `hermes-goat-web`, אך תיקיית ה־plugin וה־skill נקראות `goat-web` (`plugins/goat-web/plugin.yaml:1–4`; `skills/goat-web/SKILL.md:1–6`). משתמש אינו יודע איזה שם להשתמש בפקודות ניהול, והניסוח הציבורי לגבי בדיקת אבטחה חזק מהסטטוס המוצהר בתוך החבילה.

**תיקון מוצע:** ליישר את טענת האבטחה לראיות ולסטטוס אישור השחרור בפועל; להוסיף טבלת זהויות מפורשת (שם האוסף, שם תיקיית plugin, `plugin.yaml` name, שם ה־skill) ולהשתמש בשמות המדויקים בעקביות בפקודות install/validate/enable/doctor.

---

**היקף ואימות:** בדיקת מסמכים וקוד רישום לצורך השוואת חוזי דוגמאות בלבד; לא בוצעה התקנה או קריאת רשת, ולא שונו מקורות.
