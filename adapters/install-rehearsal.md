# GOAT — חזרה יבשה ותכנית התקנה חיה

**עדכון 2026-10-09 — תיקוני אריזה שבוצעו (רק scratch/goat-ultimate, scratch/goat-packs):**
- **registry:** הועתק ל-`skills/goat-ultimate/registry/capabilities.json` כמראה זהה ל-`registry/capabilities.json` (keep both); `SKILL.md` עודכן להפנות לשני הנתיבים. בדיקת `diff` — identical.
- **שם plugin:** הובהר — התיקייה `goat-web` מכילה `plugin.yaml` עם `name: hermes-goat-web` (ID מוצהר `hermes-goat-web`); פקודות Hermes משתמשות ב-ID `hermes-goat-web` (למשל `hermes plugins validate goat-web/plugins/goat-web` מאמת את `hermes-goat-web`).
- **ניתוב:** `SKILL.md` הורחב עם `goat_probe` (helper reachability) + טבלת החלטה, ו-`answer_synth`/`search_filters`/`deep_verticals` כ-future/route (לא קנוני עד רישום ב-registry).
- **אבטחה:** נוספה הערת SECURITY ב-`SKILL.md` עם קישור ל-gate results: `audit_staging.py` OK, `fuzz_gate.py` 4,288/0, unittest 51/51 + 11/11; לא סקירה מלאה, דורש אישור אנושי.

**מצב:** תכנית בלבד; לא בוצעה התקנה או כתיבה ללייב. GO/NO-GO כרגע: **CONDITIONAL-GO** לאחר תיקוני האריזה לעיל — עדיין דורש baseline חדש ו-`hermes plugins validate`/`doctor` בחלון תחזוקה לפני כתיבה ללייב.

## מה נחשב GOAT כאן

החבילה מורכבת מ־`goat-ultimate` (skill לניתוב) ומ־`goat-web` (skill + plugin שמצהיר על `goat_search`, `goat_extract`, `goat_crawl`, `goat_probe`). אין כאן בקשה להוסיף MCP. כל התקנה עתידית מוגבלת לשני skills ול־plugin אחד; היא לא כוללת החלפה או עדכון גורף של ה־skills הקיימים.

## מצב הלייב — קריאה בלבד

- `HERMES_HOME` של הפרופיל הפעיל נפתר ל־the active Hermes home; `hermes config path` החזיר the active config.yaml. לא נקרא תוכן config ולא נגעו בו.
- `hermes skills list` החזיר **247 enabled, 0 disabled**: 53 builtin, 178 local, 16 hub-installed. `goat-ultimate` ו־`goat-web` אינם מופיעים.
- `hermes plugins list --json` החזיר **62 plugins**: 56 enabled ו־6 `not enabled`; אין רשומת GOAT.
- `hermes mcp list` מציג MCP יחיד, `donsetch_hardened`, במצב **disabled**. אין לשנותו.
- בדיקת קיום שמות היעד תחת the skills/ and plugins/ directories of the active home החזירה שאין כרגע תיקיות `goat-ultimate`, `goat-web` או `hermes-goat-web`.
- **סתירה שחייבים ליישב לפני שינוי:** `goat-ultimate/registry/live-inventory.json` מתעד 246 skills (53 builtin, 177 local, 15 official, 1 skills.sh), בעוד הקריאה הנוכחית ל־CLI מחזירה 247. ברישומי ה־plugins וה־MCP המספרים כן תואמים (62 ו־MCP disabled יחיד). עד לקריאת baseline חדשה ומאושרת, יש לשמר את *כל* הקיים ולא להניח שהמספר הוא 246 או 247.

## חזרה יבשה שבוצעה — `tmp` בלבד

הועתקו שתי עצי הייחוס לתיקייה זמנית תחת a temporary directory outside any Hermes home; החזרה השתמשה ב־`HERMES_HOME`, `HOME`, `XDG_CONFIG_HOME` ו־`TMPDIR` זמניים. כל הבדיקות הורצו על ההעתקים. תיקיות החזרה נמחקו בסיום, ו־hash של כל קובצי המקור בשני עצי הייחוס נשאר זהה.

- `goat-ultimate` (9 קבצים): `unittest` — **4/4 PASS**.
- `goat-browser-staging` (30 קבצים): בהרצה הסופית `unittest` — **51/51 PASS**; בנוסף 10 הרצות מלאות עם `PYTHONHASHSEED` שונים — **10/10 PASS**. בשתי הרצות אבחון מוקדמות נכשל אותו test יחיד, `test_generated_urls_include_raw_and_percent_encoded_credentials`; הוא לא שוחזר בעשר ההרצות החוזרות. יש להתייחס לכך כאנומליה ולחזור על בדיקת היחידה בחלון ההתקנה.
- `scripts/fuzz_gate.py` — **4,288 מקרים, 0 כשלים** (2,600 URLs, 1,683 redirects, 5 קלטים שאינם מחרוזות; 284 מקרי userinfo בדוח הריצה).
- `scripts/audit_staging.py` — **OK: no staging findings**. זה audit היוריסטי מוגבל, לא סריקת סודות מלאה.
- חיבור למאמת ה־plugin האמיתי של Hermes, נגד ההעתק הזמני (snapshot ישן): `hermes plugins validate … --json` נכשל כצפוי (**exit 1**): `no plugin.yaml ...` — **עדכון 2026-10-09:** בעץ הנוכחי (`goat-public/goat-web`, `goat-browser-staging`) קיים `plugins/goat-web/plugin.yaml` עם `name: hermes-goat-web`; נדרש rerun של `hermes plugins validate goat-web/plugins/goat-web` בחלון ההתקנה (צפי: pass).
- בדיקת rollback בסביבת `HERMES_HOME` זמנית: הועתקו רק יעדי GOAT המתוכננים, הוסרו לאחר מכן, וה־snapshot הזמני חזר בדיוק ל־baseline שנלקח אחרי אתחול המאמת. hash של config בדיקה ו־fixtures קיימים נשארו ללא שינוי; כל יעדי GOAT נעדרו אחרי rollback. המאמת יצר קובצי runtime ברירת־מחדל בתוך ה־HERMES_HOME הזמני בלבד; הם נמחקו יחד עם סביבת החזרה.
- `references/qa-report.md` ישן ביחס לעץ: הוא מצהיר על 38 בדיקות/27 קבצים, בעוד העתק העץ הנוכחי מכיל 51 בדיקות/30 קבצים. יש לעדכן ראיות QA רק בעץ עבודה חדש ומאושר; לא לערוך את עצי הייחוס האלה.

## חסמי GO/NO-GO לפני התקנה

1. **תוקן 2026-10-09 — ה־plugin כעת חבילת Hermes תקינה במקור הציבורי.** ב-`goat-web/plugins/goat-web/plugin.yaml` קיים `name: hermes-goat-web`, `entrypoint: __init__:register` וארבעת הכלים `goat_search`/`goat_extract`/`goat_crawl`/`goat_probe` (גם `hermes-goat-web.plugin.json` תואם). הריצה היבשה הישנה (`no plugin.yaml`) התייחסה ל-snapshot ישן/ל-tmp שגוי; בעץ הנוכחי (`goat-browser-staging`/`goat-public/goat-web`) המניפסט קיים. נדרש עדיין `hermes plugins validate` מחדש בחלון ההתקנה לפני כתיבה ללייב.
2. **תוקן 2026-10-09 — אי-התאמת שם הוסברה ותועדה:** התיקייה נקראת `goat-web` וה-manifest מצהיר `name: hermes-goat-web` — זהו ה-ID המוצהר. הותקנה טבלת זהויות: `dir goat-web` → `ID hermes-goat-web` → `installed at $HERMES_HOME/plugins/hermes-goat-web/`; פקודות `validate`/`enable`/`doctor` משתמשות ב-`hermes-goat-web`. ראה `goat-ultimate/skills/goat-ultimate/SKILL.md` סעיף GOAT web plugin identity.
3. **תוקן 2026-10-09 — נתיב registry הוכפל לתאימות:** `registry/capabilities.json` נשאר קנוני בשורש וגם הועתק כמראה זהה ל-`skills/goat-ultimate/registry/capabilities.json` (keep both). `SKILL.md` עודכן להפנות לשני הנתיבים; `diff` identical. מיפוי ההתקנה להלן כבר תואם (שני הנתיבים זהים).
4. `plugins/goat-web/adapters.py` מסומן בקוד עצמו כ־placeholder (חילוץ טקסט/RSS חלקי). אין להתקין אותו או להציגו כמימוש production. יש לבנות ולבדוק רישום כלים תקין על בסיס `goat_tools.py` ו־`url_gate.py` בלבד, בלי לשנות את עצי הייחוס הנוכחיים.
5. אין כרגע URL/commit SHA בלתי־משתנה לחבילת plugin תקינה. `hermes plugins install` מקבל קטלוג או Git URL/owner-repo, לא נתיב תיקייה מקומי. אין להמציא מקור או SHA; אם נשארים offline, נדרשת שיטת התקנה מקומית מאושרת ומתועדת.

## מיפוי קבצים להתקנה — רק אחרי תיקון ואישור

| מקור בעץ הייחוס | יעד עתידי | הערה |
|---|---|---|
| `goat-ultimate/skills/goat-ultimate/SKILL.md` | `$HERMES_HOME/skills/goat-ultimate/SKILL.md` | skill אחד, לא עדכון של skills קיימים. |
| `goat-ultimate/registry/capabilities.json` | `$HERMES_HOME/skills/goat-ultimate/registry/capabilities.json` | חיוני כדי שהנתיב היחסי שה־skill מציין יתקיים. |
| `goat-browser-staging/skills/goat-web/SKILL.md` וכל שלושת קובצי `skills/goat-web/references/*.md` | `$HERMES_HOME/skills/goat-web/` תוך שמירת המבנה היחסי | לא להעתיק רק את SKILL.md ולהשאיר קישורי references שבורים. |
| חבילת plugin מתוקנת: manifest Hermes מוכר, רישום/entrypoint, `goat_tools.py`, `url_gate.py`, ורישיון `LICENSE` | `$HERMES_HOME/plugins/<plugin-id-מאושר>/` | אין לבצע העתקה חיה מהעץ הנוכחי. יש לכלול רק קוד שנבדק; ה־ID ייקבע אחרי תיקון הסתירה לעיל. |

להשאיר מחוץ ל־HERMES_HOME: `registry/live-inventory.json` (תמונת מצב פנימית), `references/merge-notes.md`, `references/qa-report.md`, `references/paid-adapters.md`, קובצי `OUTCOME_LEDGER`/`PROVENANCE`, `README`, `.github`, `tests`, `scripts`, ו־`adapters.py`. ה־sidecar הנוכחי אינו תחליף ל־manifest Hermes.

## סדר ביצוע עתידי

1. **אישור והקפאת baseline:** בחלון תחזוקה, לקרוא מחדש בלבד את `hermes skills list`, `hermes plugins list --json`, `hermes mcp list` ולשמור ספירות/שמות/מצבי enabled בלי endpoints, args או סודות, וגם manifest שמות+SHA-256 של קובצי ה־skills/plugins הקיימים (hash בלבד; לא להעתיק תוכן). ליישב במפורש 246 מול 247. לעצור אם יעד כלשהו כבר קיים או השתנה מאז החזרה.
2. **סגירת חסמי חבילה בעץ עבודה נפרד:** לבחור plugin ID יחיד; להוסיף manifest Hermes אמיתי ורישום ארבעת הכלים; לוודא ש־registry נמצא במקום שה־skill מצפה לו. אין לשנות את שני עצי הייחוס במשימה הזו. להצמיד מקור ו־SHA מלא, להריץ tests, fuzz, audit ו־`hermes plugins validate`; נדרשת תוצאה תקינה לפני כל כתיבה ללייב.
3. **גיבוי ממוקד:** לשמור מחוץ ל־`skills/` ול־`plugins/` snapshot/hash של יעדי GOAT אם קיימים, ושל רשומת install metadata של plugin אם CLI משנה אותה. לתעד במפורש אילו יעדים נעדרו. אין לגבות או להעתיק סודות, state, sessions או MCP config.
4. **התקנת plugin במצב disabled:** לאחר שיש מקור immutable תקין, להשתמש ב־`hermes plugins install <catalog-id-or-repo> --ref <40-hex-commit> --no-enable`. אם המקור נשאר מקומי בלבד, לא להשתמש בפקודה כאילו היא תומכת בנתיב מקומי; לעצור עד לשיטת התקנה מקומית שאושרה. להריץ `hermes plugins validate <plugin-path>` ו־`hermes plugins doctor <plugin-id> --ci`; לוודא capabilities לפני enable.
5. **התקנת שני ה־skills:** להוסיף את שתי התיקיות והקבצים מהמיפוי לעיל ללא `--force`, ללא overwrite וללא sync/update גורף. CLI `hermes skills install` אינו מקבל תיקייה מקומית; לעץ offline יש להשתמש בהעתקה מקומית מבוקרת בלבד. לבצע העתקה אטומית מ־staging מאושר; אם היעד קיים — לעצור ולא לדרוס.
6. **Readback לפני הפעלה:** לוודא שה־plugin רשום disabled, ארבעת tool names מוצגים בפועל, שני ה־skills מזוהים, וה־registry נגיש מהנתיב היחסי. בדיקות רשת אמיתיות לא לבצע בלי אישור נפרד; להשתמש ב־fake transport בבדיקות staging.
7. **הפעלה מדורגת:** רק באישור מפורש, להפעיל את plugin ב־`hermes plugins enable <plugin-id>` ולפתוח session חדש לבדיקת routing. אין restart ל־gateway כחלק מהתכנית; אם נדרש restart, לעצור ולבקש אישור/חלון תחזוקה נפרד.
8. **בדיקת post-install:** לקרוא שוב את שלוש רשימות ה־CLI, להשוות את manifest ה־SHA-256 של כל ה־skills/plugins הקיימים מול ה־baseline, ולוודא שלא השתנו; לבדוק ש־MCP עדיין אותו שרת יחיד disabled. עם baseline נוכחי 247 ושני skills חדשים, הציפייה היא 249 skills. Plugin נוסף ייתן 63 plugins; לפני enable: 56 enabled/7 not enabled, ואחרי enable: 57 enabled/6 not enabled. אם baseline המאושר חוזר ל־246, להתאים את הציפיות ל־248 skills. MCP נשאר ללא שינוי.

## Rollback חי — רק אם שלב התקנה עתידי נכשל

1. אם ה־plugin הופעל, `hermes plugins disable <plugin-id>`; אין restart אוטומטי. לעצור יצירת sessions חדשים עד שה־rollback נקרא חזרה.
2. להסיר **רק** את שני יעדי GOAT שנוספו ואת תיקיית plugin המדויקת. אם יעד היה קיים לפני ההתקנה, לשחזר אותו מה־snapshot ולוודא hash/רשימת קבצים תואמים. לשחזר/להסיר רק את רשומת install metadata של GOAT, לא את כל קובץ metadata.
3. לא למחוק `$HERMES_HOME/skills`, `$HERMES_HOME/plugins`, ולא להחזיר backup מלא של `config.yaml`. לבדוק ש־hash של `config.yaml` נשאר זהה; אם השתנה, לעצור ולבצע תיקון ממוקד אחרי בדיקת diff.
4. לקרוא שוב skills/plugins/MCP: כל ה־skills וה־plugins הקודמים באותו baseline, GOAT לא מותקן/מופעל, ו־MCP עדיין disabled. אם קריאת החזרה אינה תואמת — אין לטעון שה־rollback הושלם.

## מה לא לגעת

- לא לשנות, לעדכן, למחוק, להעביר או לדרוס אף אחד מה־skills הקיימים (247 לפי ה־CLI הנוכחי; snapshot אחר מדווח 246). לא להשתמש ב־`hermes skills update`, `uninstall`, `reset`, `--force` או bulk sync כחלק מההתקנה.
- לא להוסיף/להסיר/להתקין/לבדוק/להגדיר MCP; לא לערוך `mcp_servers`; להשאיר את `donsetch_hardened` disabled.
- לא לגעת ב־the active config.yaml, `.env`, `auth.json`, פרופילים, sessions, memories, state DB, gateway, logs או credentials. אין keys, cookies, headers או secrets בחבילה או בפקודות.
- לא להפעיל paid backends, לא לבצע קריאות רשת, לא לפרסם repository ולא להפעיל gateway מחדש במסגרת החזרה הזו.
- לא לערוך את `goat-ultimate` או `goat-browser-staging`: שניהם read-only refs. במסגרת תת־משימה זו נכתב רק מסמך זה; קבצים אחרים בתיקיית `goat-packs` נשארו ללא מגע.
