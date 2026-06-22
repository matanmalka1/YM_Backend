> **Legacy unverified frontend screen spec. Not source of truth.**
> Use `../docs/frontend/` for frontend rules, `../docs/domains/` for product/domain behavior, and current frontend code for implemented UI state.
> This file remains in `backend/docs` only as historical/reference screen inventory.

## Scope
This file owns only:
- Draft screen specifications whose relationship to the current frontend implementation is not yet verified.

This file must not contain:
- Canonical frontend behavior.
- Canonical domain behavior.
- Backend architecture rules.

Source of truth: reference

# איפיון מסכים — Frontend CRM

Status: reference/historical screen inventory. This file is kept under `backend/docs` but does not own frontend behavior or backend API contracts.

Last backend endpoint spot-check: 2026-05-29. Claims about current frontend implementation were not fully re-verified in this backend-doc audit. Treat route/API statements here as screen-context notes only; canonical endpoint contracts are the backend routers/OpenAPI and frontend contracts in the frontend codebase.

## מטרה

מסמך זה הוא inventory/reference לאיפיון מסכים ב־`../frontend`.
הוא אינו מקור אמת מחייב ל־UX, הרשאות, נתונים או פעולות.
המטרה היא לשמר נקודות בדיקה ופערים ידועים עד שיועברו למסמך frontend קנוני.

## תבנית איפיון אחידה לכל מסך

- מטרה עסקית
- route contract: path, route params, query params, deep links
- entry points / exit paths
- מי משתמש בו: `ADVISOR` / `SECRETARY` / ציבורי
- הרשאות: `view/create/edit/delete/export/approve/bulk/execute`
- נתונים מוצגים
- data contract: מקורות נתונים, required מול optional
- CTA ראשי / CTA משני
- פעולות מותרות
- פעולות הרסניות: confirm, נעילות לפי סטטוס, guardrails
- פילטרים, מיון, חיפוש, פגינציה
- URL state: מה נשמר ב־URL, מה לוקאלי, מה נשמר רק ב־session
- מצבי ריק / שגיאה / טעינה
- מצבי הצלחה / system feedback
- refresh behavior
- unsaved changes behavior
- responsive behavior
- accessibility
- תלותים במסכים אחרים
- audit visibility
- open questions
- פערים, כפילויות ושבירות נוכחית

## עקרונות רוחביים

- כל מסך רשימה חייב להגדיר במפורש: פילטרים, מיון, חיפוש, פגינציה, empty state, error state.
- כל מסך detail חייב להגדיר: מזהה כניסה, invalid-id state, loading state, not-found/error state.
- כל מסך עם טאבים חייב להגדיר האם הטאב נשמר ב־URL.
- כל מסך חייב להגדיר הרשאות ברמת צפייה וברמת פעולה.
- כל מסך חייב להגדיר אילו פרמטרים נשמרים ב־URL ואילו נשארים לוקאליים.
- כל פעולה חייבת להגדיר feedback צפוי: toast, inline alert, optimistic update או retry.
- כל מסך חייב להגדיר מה קורה ב־refresh, back/forward ו־deep link ישיר.
- כל מסך רשימה חייב להגדיר חוקי bulk selection: מתי selection נשמר, מתי מתאפס.
- כל מסך חייב להגדיר התנהגות מובייל/טאבלט אם הוא נתמך מחוץ לדסקטופ.
- אין להסתמך על "מה שהקומפוננטה עושה כרגע" במקום על חוזה מסך כתוב.

## מסכים

### 1. Login

- מטרה עסקית: כניסה מאובטחת למערכת עבור משתמשי משרד.
- מי משתמש בו: כל משתמש לא מזוהה.
- נתונים מוצגים: שדות אימייל, סיסמה, שגיאת שרת, מצב טעינה.
- פעולות מותרות: התחברות, הצגת/הסתרת סיסמה.
- פילטרים, מיון, חיפוש, פגינציה: אין.
- מצבי ריק / שגיאה / טעינה:
  - מצב רגיל: טופס התחברות.
  - מצב טעינה: כפתור במצב התחברות.
  - מצב שגיאה: הודעת שגיאה מהשרת.
  - מצב redirect: משתמש מחובר מועבר ל־`/`.
- תלותים במסכים אחרים: Dashboard לאחר login מוצלח.
- פערים, כפילויות ושבירות נוכחית:
  - המסך עבר לעיצוב דו־פאנלי ממותג ונשען על הפרימיטיבים האחידים של המערכת (`Input`, `Button`, `Alert`).
  - ה־toggle להצגת/הסתרת סיסמה עדיין ממומש מקומית בתוך השדה.

### 2. Dashboard

- מטרה עסקית: תמונת מצב משרדית ופעולות מהירות לפי תפקיד.
- מי משתמש בו: `ADVISOR`, `SECRETARY`.
- נתונים מוצגים: stats, attention items, quick actions, season summary, advisor today.
- פעולות מותרות:
  - `ADVISOR`: quick actions, אישורי confirm.
  - `SECRETARY`: צפייה בלבד בגרסה מצומצמת.
- פילטרים, מיון, חיפוש, פגינציה: אין.
- מצבי ריק / שגיאה / טעינה:
  - skeleton לטעינה.
  - denied state.
  - error state.
- תלותים במסכים אחרים: binders, deadlines, annual reports, operational flows.
- פערים, כפילויות ושבירות נוכחית:
  - המסך נשען על branch לפי role view, אך בפועל כבר יש חלוקה יציבה יותר: attention panel משותף, ו־operational/season/today ליועץ בלבד.
  - חוזה המסך עדיין לא מנסח במפורש אילו אזורים קבועים לכל role ואילו אזורים מותנים.

### 3. Binders

- מטרה עסקית: ניהול מחזור חיים של קלסרים.
- מי משתמש בו: `ADVISOR`, `SECRETARY`.
- נתונים מוצגים: רשימת קלסרים, counters, קלסר נבחר, deep link לקלסר.
- פעולות מותרות:
  - קליטת חומר.
  - פתיחת detail drawer.
  - סימון מוכן.
  - ביטול סימון מוכן.
  - החזרה.
  - מסירה.
  - מחיקה.
  - bulk ready.
- פילטרים, מיון, חיפוש, פגינציה:
  - פילטרים לפי סטטוס ותקופה.
  - פגינציה קיימת.
  - מיון אינו מוגדר כמנגנון מסך מפורש.
- מצבי ריק / שגיאה / טעינה:
  - loading בטבלה.
  - error בטבלה.
  - empty state עם CTA לקליטת חומר.
  - dialogs ל־return/delete/bulk/handover.
- תלותים במסכים אחרים: clients, businesses, annual reports.
- פערים, כפילויות ושבירות נוכחית:
  - page כבד עם orchestration רב.
  - detail ו־receive חולקים drawer behavior.
  - state מפוזר בין table, drawer ו־dialogs.

### 4. Clients

- מטרה עסקית: ניהול רשימת לקוחות מלאה.
- מי משתמש בו: `ADVISOR`, `SECRETARY`.
- נתונים מוצגים: רשימת לקוחות, stats לפי status, total.
- פעולות מותרות:
  - `ADVISOR`: יצירה, עריכה, import/export, restore.
  - `SECRETARY`: צפייה בלבד.
- פילטרים, מיון, חיפוש, פגינציה:
  - פילטרים.
  - פגינציה.
  - page size.
  - sorting קיים ברמת feature אך לא מוגדר כאן כחוזה מסך מפורש.
- מצבי ריק / שגיאה / טעינה:
  - readonly alert.
  - empty state עם CTA.
  - deleted-client conflict dialog.
  - confirm dialog לפעולות ממתינות.
- תלותים במסכים אחרים: ClientDetails, ImportExport.
- פערים, כפילויות ושבירות נוכחית:
  - יותר מדי מודלים במסך אחד: create, edit, restore, import/export.
  - orchestration כבד ברמת page.

### 5. Client Details

- מטרה עסקית: מעטפת 360 ללקוח.
- מי משתמש בו: `ADVISOR`, `SECRETARY`.
- נתונים מוצגים:
  - פרטי לקוח.
  - binders.
  - charges.
  - notes.
  - טאבים: details, documents, deadlines, timeline, vat, advance-payments, annual-reports, communication, finance.
- פעולות מותרות:
  - עדכון לקוח.
  - מחיקת לקוח.
  - יצירת עסק.
  - יצירת חיוב מתוך מסך לקוח.
  - קליטת קלסר מתוך מסך לקוח.
  - פעולות פנימיות לפי טאב.
- פילטרים, מיון, חיפוש, פגינציה:
  - לא ברמת המעטפת.
  - קיימים בתוך טאבים מסוימים.
- מצבי ריק / שגיאה / טעינה:
  - invalid id.
  - loading.
  - error / missing client.
  - readonly alert להרשאות.
- תלותים במסכים אחרים:
  - documents.
  - deadlines.
  - timeline.
  - VAT.
  - advance payments.
  - annual reports.
  - authority contacts.
  - communication.
  - finance.
  - reminders.
  - notifications.
  - signature requests.
- פערים, כפילויות ושבירות נוכחית:
  - active tab עדיין לא מנוהל ב־URL בזמן ניווט פנימי בתוך המסך.
  - יש route-level deeplink לחלק מהטאבים (`documents`, `deadlines`, `timeline`, `vat`, `advance-payments`, `annual-reports`), אבל מעבר ידני בין טאבים לא מעדכן route.
  - נוספו בפועל טאבי `communication` ו־`finance`, אך אין להם deep link ייעודי.
  - refresh או שיתוף לינק שומרים הקשר חלקי בלבד.

### 6. Business Details

- מטרה עסקית: תצוגת פרטי עסק תחת לקוח.
- מי משתמש בו: `ADVISOR`, `SECRETARY`.
- נתונים מוצגים: פרטי עסק, סטטוס, תאריכים, לקוח מקושר, notes.
- פעולות מותרות: עריכת notes לפי הרשאה.
- פילטרים, מיון, חיפוש, פגינציה: אין.
- מצבי ריק / שגיאה / טעינה:
  - invalid id.
  - loading.
  - error.
- תלותים במסכים אחרים: ClientDetails, Notes.
- פערים, כפילויות ושבירות נוכחית:
  - המסך כיום ממומש כ־summary card + business notes בלבד.
  - אם יתווספו פעולות עסק, המבנה הנוכחי ידרוש refactor.

### 7. Search

- מטרה עסקית: חיפוש גלובלי על פני ישויות מערכת.
- מי משתמש בו: `ADVISOR`, `SECRETARY`.
- נתונים מוצגים: תוצאות חיפוש כלליות, תוצאות מסמכים.
- פעולות מותרות:
  - חיפוש חופשי.
  - פתיחת advanced filters.
  - reset לחיפוש.
- פילטרים, מיון, חיפוש, פגינציה:
  - query חופשי.
  - client_name.
  - id_number.
  - binder_number.
  - פגינציה.
- מצבי ריק / שגיאה / טעינה:
  - no filter state.
  - no results state.
  - error alert.
  - loading בטבלה.
- תלותים במסכים אחרים: clients, binders, documents.
- פערים, כפילויות ושבירות נוכחית:
  - results ו־documents מוצגים בשני אזורים שונים.
  - אין מודל תוצאות אחיד למסך חיפוש.

### 8. Charges

- מטרה עסקית: ניהול חיובים ופעולות גבייה.
- מי משתמש בו: `ADVISOR`, `SECRETARY`.
- נתונים מוצגים: רשימת חיובים, summary stats, selected ids.
- פעולות מותרות:
  - `ADVISOR`: יצירה, פעולות שורה, פעולות bulk, detail drawer.
  - `SECRETARY`: צפייה בלבד.
- פילטרים, מיון, חיפוש, פגינציה:
  - פילטרים.
  - פגינציה.
  - page size.
  - status summary filters.
- מצבי ריק / שגיאה / טעינה:
  - readonly alert.
  - empty state.
  - create error.
  - loading/error בטבלה.
- תלותים במסכים אחרים: ClientDetails, actions engine.
- פערים, כפילויות ושבירות נוכחית:
  - row actions ו־bulk actions חיים יחד במסך מורכב.
  - state של selection/action loading רגיש להתנגשויות.

### 9. Annual Reports List

- מטרה עסקית: ניהול עונת דוחות שנתיים.
- מי משתמש בו: בעיקר `ADVISOR`.
- נתונים מוצגים: season summary, overdue reports, filtered reports by tax year.
- פעולות מותרות:
  - יצירת דוח חדש.
  - פתיחת דוח קיים.
- פילטרים, מיון, חיפוש, פגינציה:
  - פילטרים.
  - אין פגינציה מפורשת במסך.
- מצבי ריק / שגיאה / טעינה:
  - loading.
  - error.
  - empty state לשנה ללא דוחות.
- תלותים במסכים אחרים: Annual Report Detail.
- פערים, כפילויות ושבירות נוכחית:
  - naming לא עקבי: hook בשם Kanban אך UI מבוסס טבלה/summary.
  - המסך נשען על `SeasonReportsTable`, `SeasonSummaryCards` ו־`SeasonProgressBar`, ולכן בפועל מדובר במסך season summary + table ולא kanban.
  - הרשאות לא מנוסחות בצורה גלויה במסך.

### 10. Annual Report Detail

- מטרה עסקית: עבודה מלאה על דוח שנתי.
- מי משתמש בו: בעיקר `ADVISOR`.
- נתונים מוצגים:
  - overview.
  - financials.
  - tax.
  - deductions.
  - documents.
  - timeline.
  - charges.
  - report status.
- פעולות מותרות:
  - save.
  - export PDF.
  - transitions.
  - update detail.
  - add/complete schedule.
  - delete report.
- פילטרים, מיון, חיפוש, פגינציה: אין.
- מצבי ריק / שגיאה / טעינה:
  - loading.
  - error / missing report.
  - delete confirm.
- תלותים במסכים אחרים:
  - documents.
  - timeline.
  - charges.
  - client context.
- פערים, כפילויות ושבירות נוכחית:
  - active section לא נשמר ב־URL.
  - המסך עבר למבנה panel עם tab bar עליון ו־status strip, אך state הניווט נשאר לוקאלי.
  - מסך כבד מאוד עם state orchestration רב.
  - מסך detail מורכב אך לא מוגדר כחוזה מסך מפורט ברמת subsection.

### 11. Tax Calendar

- מטרה עסקית: ניהול מועדי מס ומעקב הגשה.
- מי משתמש בו: `ADVISOR`, `SECRETARY`.
- נתונים מוצגים: deadlines, submission stats, selected deadline.
- פעולות מותרות:
  - `ADVISOR`: create, generate, edit, delete, complete, reopen.
  - `SECRETARY`: צפייה.
- פילטרים, מיון, חיפוש, פגינציה:
  - פילטרים.
  - פגינציה.
- מצבי ריק / שגיאה / טעינה:
  - loading page.
  - error alert.
  - drawer לפרטי מועד.
  - modals ליצירה/עריכה/generate.
- תלותים במסכים אחרים: dashboard/tax widgets, client workflows.
- פערים, כפילויות ושבירות נוכחית:
  - כותרת המסך בפועל היא "דוחות מס", בעוד שהישות והתוכן הם מועדי מס.
  - מסך משלב entity management עם operational dashboard.

### 12. Advance Payments

- מטרה עסקית: מעקב מקדמות ודוח גבייה.
- מי משתמש בו: `ADVISOR`, `SECRETARY`.
- נתונים מוצגים:
  - KPI overview.
  - rows לפי לקוח/חודש/סטטוס.
  - report view.
- פעולות מותרות:
  - מעבר בין overview ל־report.
  - drilldown ללקוח.
- פילטרים, מיון, חיפוש, פגינציה:
  - year.
  - month.
  - status.
  - page.
  - tab דרך query params.
- מצבי ריק / שגיאה / טעינה:
  - loading.
  - error.
  - empty table.
- תלותים במסכים אחרים: ClientDetails, reports.
- פערים, כפילויות ושבירות נוכחית:
  - שתי תצוגות שונות מאוד בתוך אותו מסך: `overview` ו־`report`.
  - התצוגה (`tab`) והפילטרים (`year`, `month`, `status`, `page`) נשמרים ב־query params.
  - ניהול URL עדיין ידני ולא אחיד עם כל שאר מסכי הרשימות.

### 13. VAT Work Items

- מטרה עסקית: ניהול תיקי מע"מ חודשיים ברמת לקוח.
- מי משתמש בו: `ADVISOR`, `SECRETARY`.
- נתונים מוצגים: work items, status stats, urgency badges.
- פעולות מותרות:
  - פתיחת תיק.
  - פעולות שורה.
  - כניסה לתיק מע"מ.
- פילטרים, מיון, חיפוש, פגינציה:
  - פילטרים.
  - פגינציה.
  - page size.
- מצבי ריק / שגיאה / טעינה:
  - loading.
  - error.
  - readonly alert.
  - empty state.
  - create modal.
- תלותים במסכים אחרים: VAT Work Item Detail, ClientDetails.
- פערים, כפילויות ושבירות נוכחית:
  - כותרת המסך בפועל היא `דוחות מע"מ (לקוח)` ולא `VAT Work Items`.
  - create flow תלוי גם URL params (`create`, `client_id`, `period`) וגם local state.
  - קיימת מוטציה ישירה על `URLSearchParams` בתוך ה־effect של פתיחת create modal, מה שמגדיל רגישות לשבירות.

### 14. VAT Work Item Detail

- מטרה עסקית: עבודה בתוך תיק מע"מ.
- מי משתמש בו: `ADVISOR`, `SECRETARY`.
- נתונים מוצגים:
  - summary.
  - income invoices.
  - expense invoices.
  - history.
  - filed banner.
- פעולות מותרות:
  - הזנת חשבוניות.
  - עריכת חשבוניות.
  - פעולות הגשה לפי סטטוס.
  - מעבר בין טאבים.
- פילטרים, מיון, חיפוש, פגינציה:
  - טאב ב־URL.
  - אין פגינציה ברמת page.
- מצבי ריק / שגיאה / טעינה:
  - invalid id redirect.
  - loading skeleton.
  - error alert.
- תלותים במסכים אחרים: VAT list, client VAT context.
- פערים, כפילויות ושבירות נוכחית:
  - זה אחד המסכים היחידים עם tab sync מלא ב־URL באמצעות `?tab=`.
  - מדגיש חוסר אחידות מול Client Details ו־Annual Report Detail.

### 15. VAT Compliance Report

- מטרה עסקית: דוח ניהולי לציות מע"מ.
- מי משתמש בו: בעיקר `ADVISOR`.
- נתונים מוצגים:
  - compliance per client.
  - stale pending items.
  - year selector.
- פעולות מותרות: החלפת שנה.
- פילטרים, מיון, חיפוש, פגינציה:
  - שנה בלבד.
  - אין חיפוש.
  - אין פגינציה.
  - אין sorting גלוי.
- מצבי ריק / שגיאה / טעינה:
  - loading.
  - error.
  - no data for year.
- תלותים במסכים אחרים: VAT operational screens.
- פערים, כפילויות ושבירות נוכחית:
  - טבלאות HTML ידניות במקום פרימיטיב אחיד.
  - אין drilldown מהדוח למסך לקוח/תיק.

### 16. Reminders

- מטרה עסקית: ניהול תזכורות רוחביות.
- מי משתמש בו: `ADVISOR`, `SECRETARY`.
- נתונים מוצגים:
  - reminders.
  - pending/sent counts.
  - linked entities ליצירת reminder.
- פעולות מותרות:
  - יצירת תזכורת.
  - ביטול.
  - סימון כנשלח.
  - פתיחת drawer.
- פילטרים, מיון, חיפוש, פגינציה:
  - status filter.
  - type filter.
  - search.
  - אין פגינציה במסך.
- מצבי ריק / שגיאה / טעינה:
  - loading.
  - error.
  - no reminders.
  - no results for filter.
- תלותים במסכים אחרים:
  - binders.
  - charges.
  - tax calendar.
  - annual reports.
  - advance payments.
- פערים, כפילויות ושבירות נוכחית:
  - מסך אינטגרטיבי עם הרבה תלותים רוחביים.
  - המסך נשען על `PageStateGuard`, summary cards, filters bar, table ו־drawer, אך עדיין ללא פגינציה.
  - סיכון גבוה לשבירה כשדומיין אחד משתנה.

### 17. Signature Requests

- מטרה עסקית: ניהול בקשות חתימה בכלל הלקוחות.
- מי משתמש בו: `ADVISOR`, `SECRETARY`.
- נתונים מוצגים:
  - requests.
  - draft/pending/terminal counts.
  - signing URLs.
  - business lookup.
- פעולות מותרות:
  - יצירת בקשה.
  - שליחה.
  - ביטול.
  - צפייה ב־audit.
  - toggle להצגת ארכיון.
- פילטרים, מיון, חיפוש, פגינציה:
  - show all / active only.
  - אין חיפוש.
  - אין פגינציה.
  - אין filters עשירים.
- מצבי ריק / שגיאה / טעינה:
  - loading.
  - error.
  - empty state.
- תלותים במסכים אחרים: Signing Page, ClientDetails.
- פערים, כפילויות ושבירות נוכחית:
  - מסך queue בלי יכולות חיפוש/פילטור מספקות.
  - toggle של `show all` מחליף בין active queue לארכיון חלקי, אך אינו מהווה מודל סינון עשיר.
  - columns נבנים inline ב־page ומכבידים על התחזוקה.

### 18. Users

- מטרה עסקית: ניהול משתמשים, תפקידים והרשאות.
- מי משתמש בו: `ADVISOR` בלבד.
- נתונים מוצגים: users, filters, current user context.
- פעולות מותרות:
  - create user.
  - edit user.
  - reset password.
  - activate/deactivate.
  - פתיחת audit logs.
- פילטרים, מיון, חיפוש, פגינציה:
  - filters.
  - פגינציה.
  - page size.
- מצבי ריק / שגיאה / טעינה:
  - access denied.
  - loading/error.
  - empty state.
  - confirm dialog להפעלה/השבתה.
- תלותים במסכים אחרים: Auth state, audit logs.
- פערים, כפילויות ושבירות נוכחית:
  - הרשאה נאכפת גם ב־router וגם ב־page.
  - audit logs נפתחים ב־drawer נפרד ולא כחלק אינהרנטי מהמסך הראשי.
  - כפילות באכיפת access.

### 19. Public Signing

- מטרה עסקית: חתימה ציבורית על בקשת חתימה באמצעות token.
- מי משתמש בו: חותם חיצוני.
- נתונים מוצגים:
  - פרטי בקשה לחתימה.
  - סטטוס חתימה.
  - decline reason.
- פעולות מותרות:
  - approve.
  - decline.
  - confirm approve.
  - confirm decline.
- פילטרים, מיון, חיפוש, פגינציה: אין.
- מצבי ריק / שגיאה / טעינה:
  - loading.
  - error.
  - signed.
  - declined.
  - expired.
- תלותים במסכים אחרים: Signature Requests.
- פערים, כפילויות ושבירות נוכחית:
  - אין איפיון מפורש למעברי state בין ready / confirm / terminal.
  - קיימים בפועל מצבי terminal ברורים (`loading`, `error`, `signed`, `declined`) לצד `expired` וזרימת confirm כפולה.
  - שפה ויזואלית נפרדת, ללא מסמך UX משלים.

## תבניות שבירה רוחביות

### A. אחידות state management

- עדיין יש ערבוב בין `PageStateGuard`, `PageLoading`, `Alert`, `StateCard`, וטעינה ידנית.
- קיימת התכנסות חלקית לתבניות אחידות, אבל אין חוזה מסך מלא ואחיד ל־list מול detail.

### B. אחידות URL state

- `VAT Work Item Detail` שומר tab ב־URL.
- `Advance Payments` שומר `tab` ופילטרים ב־query params.
- `Client Details` מספק deeplink route-level רק לחלק מהטאבים, אבל active tab לא מסתנכרן ב־URL בניווט פנימי.
- `Annual Report Detail` לא שומר section ב־URL.
- התוצאה: deep link לא אחיד ושבירות ב־refresh/navigation.

### C. אחידות רשימות

- יש התכנסות ברורה ל־`PaginatedDataTable` ברוב מסכי ה־CRUD המרכזיים.
- עדיין קיימים `DataTable + PaginationCard` וגם טבלאות HTML ידניות ב־search, reminders, signature requests ו־VAT compliance.
- עדיין אין תבנית UX אחת שמכסה את כל מסכי list.

### D. הרשאות

- חלק מההרשאות נאכפות ב־router.
- חלק ב־page.
- חלק ב־hook.
- נדרש matrix אחד ברור: `view`, `create`, `edit`, `delete`, `execute`.

### E. מסכים שמנים

- המסכים המועמדים המרכזיים לפירוק:
  - `Clients`
  - `Binders`
  - `Charges`
  - `AdvancePayments`
  - `SignatureRequests`
  - `AnnualReportFullPanel`

## החלטות מוצר/UX מומלצות להמשך

- להגדיר חוזה אחיד למסך list.
- להגדיר חוזה אחיד למסך detail.
- להחליט שכל tab משמעותי נשמר ב־URL.
- להגדיר matrix הרשאות מסכי מערכת.
- להגדיר policy אחיד ל־URL state, refresh behavior ו־deep links.
- להגדיר system feedback אחיד לפעולות create/update/delete/bulk.
- להגדיר responsive rules אחידים למסכי table/detail/drawer.
- להגדיר audit visibility אחיד במסכים עם פעולות רגישות.
- להפריד בין screen shell, screen state, screen actions.
- לצמצם page orchestration ולהעביר ל־screen controller hooks קטנים.

## סדר עדיפויות מומלץ

1. חוזה אחיד ל־list screens.
2. URL state אחיד למסכים עם tabs.
3. matrix הרשאות מסודר לכל מסך.
4. policy אחיד ל־refresh, success feedback ו־bulk selection.
5. responsive/accessibility baseline לכל המסכים.
6. פירוק המסכים השמנים.
7. איחוד empty/loading/error states.

## נספח מוצע להשלמה רוחבית

### A. Route Contract

- לכל מסך יש להגדיר:
  - path מלא.
  - route params.
  - query params נתמכים.
  - deep links רשמיים.
  - invalid param behavior.

### B. URL State Policy

- נשמר ב־URL:
  - tab פעיל.
  - page.
  - page size.
  - sorting.
  - filters משמעותיים.
  - entity context שניתן לשתף בלינק.
- נשאר לוקאלי:
  - modal open state זמני.
  - selection זמני שאינו בר שיתוף.
  - draft inputs שעדיין לא הוחלו.
- נשמר ב־session בלבד:
  - העדפות תצוגה שאינן חלק מהקשר ניווט.

### C. Success And Feedback

- לכל פעולה יש להגדיר:
  - success toast או inline success.
  - error feedback.
  - optimistic update או refetch.
  - retry behavior.
  - post-action redirect או השארה במקום.

### D. Bulk Selection Rules

- יש להגדיר האם selection:
  - נשמר בעת pagination.
  - מתאפס בעת filter change.
  - מתאפס בעת refresh.
  - נשמר רק על הדף הנוכחי או על כל תוצאת החיפוש.

### E. Responsive And Accessibility Baseline

- responsive:
  - אילו טבלאות קורסות ל־cards.
  - אילו עמודות מוסתרות.
  - מתי drawer הופך ל־full-screen panel.
- accessibility:
  - keyboard navigation.
  - focus order.
  - dialog/drawer focus trap.
  - aria labels לשדות ופעולות.

### F. Audit Visibility

- במסכים עם פעולות רגישות יש להגדיר:
  - האם מוצג `last updated by / at`.
  - האם יש audit drawer או timeline.
  - אילו פעולות ניתנות למעקב משתמש.

### G. Glossary And Naming

- יש לאחד שמות ישויות וכותרות UI:
  - `Tax Calendar` מול `דוחות מס` מול `מועדי מס`.
  - `VAT Work Item` מול `תיק מע"מ`.
  - `Annual Reports List` מול `season summary`.
- לכל ישות מרכזית צריך שם תצוגה אחד קבוע:
  - בעברית ל־UI.
  - באנגלית פנימית לשמות feature/routes/hooks.
