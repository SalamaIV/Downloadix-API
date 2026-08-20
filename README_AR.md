# خادم Downloadix — Render وVPS

الخادم ينفّذ التنزيلات في Queue باستخدام yt-dlp وFFmpeg، ويعيد رابط الملف بعد اكتماله. الملفات تُحذف تلقائيًا بعد ساعة افتراضيًا.

## نشر Render

1. ارفع مجلد `backend` إلى مستودع GitHub جديد.
2. من Render اختر New ثم Blueprint واربط المستودع.
3. اختر ملف `render.yaml`.
4. بعد الإنشاء، ضع رابط الخدمة الكامل في `PUBLIC_BASE_URL` مثل `https://downloadix-api.onrender.com`.
5. انسخ قيمة `DOWNLOADIX_API_KEY` من إعدادات Render لاستخدامها عند ربط الموقع.

ملاحظة: الخطة Starter أنسب من الخطة المجانية للتنزيلات. التخزين المؤقت يختفي عند إعادة تشغيل الخدمة، وهذا مقصود لأن الملفات تُحذف بعد التنزيل.

## نشر VPS Ubuntu

المقترح: Ubuntu 24.04، نواتان CPU، وذاكرة 4GB، ومساحة 40GB على الأقل.

1. اربط نطاقًا فرعيًا مثل `api.example.com` بعنوان IP الخادم.
2. ثبّت Docker Engine وDocker Compose.
3. انسخ مجلد `backend` إلى الخادم.
4. انسخ `.env.vps.example` إلى `.env` وعدّل القيم.
5. شغّل `docker compose up -d --build`.
6. افحص `https://api.example.com/health`، ويجب أن يعيد `status: ok`.

## ربط الموقع

أضف قيمتي `DOWNLOADIX_API_URL` و`DOWNLOADIX_API_KEY` إلى بيئة تشغيل موقع Downloadix، ثم أعد نشر الموقع. لا تضع المفتاح داخل JavaScript في المتصفح.
