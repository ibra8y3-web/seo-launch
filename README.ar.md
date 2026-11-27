# seo-launch

ادفع أي موقع ثابت لمحركات البحث فورًا. ملف بايثون واحد، من غير أي مكتبات.

أغلب نصايح SEO بتقولك انشر واستنى أسابيع لحد ما الزواحف تيجي. seo-launch بيعمل
العكس: بيجهز صفحاتك فنيًا وبعدين *يبلغ* المحركات في نفس لحظة أي تغيير، عن طريق
بروتوكول [IndexNow](https://www.indexnow.org/) - إبلاغ مباشر تشغله بينج وYandex
وNaver وSeznam وYep.

## بصراحة

**مفيش أي أداة في الدنيا تقدر تجبر جوجل يفهرس أو يرتّب صفحتك.** اللي بيعدك بكده
بيبيعلك وهم. اللي seo-launch بيعمله إنه يشيل كل عائق فني (عناوين ووصف وcanonical
وخريطة موقع ناقصة) ويبعت إبلاغات مباشرة لكل محرك بيقبلها، عشان الاكتشاف ياخد
دقايق مش أسابيع. جوجل مشتركش في أي بروتوكول إبلاغ؛ لجوجل لسه بتأكد ملكيتك في
Search Console وتطلب الفهرسة - وseo-launch بيجهزلك ملف التحقق. زاحف جوجل عادة
بيلحق خلال أيام بعد ما بينج والباقي يبدأوا يزوروا موقعك.

## الأوامر

| الأمر | النتيجة |
| --- | --- |
| `scan` | فحص كل صفحة: عنوان، وصف، canonical، Open Graph، JSON-LD |
| `fix` | يضيف الوسوم الناقصة (آمن يتكرر كذا مرة) |
| `sitemap` | يكتب `sitemap.xml` من ملفات HTML |
| `robots` | يكتب `robots.txt` فيه رابط خريطة الموقع |
| `verify --google CODE` | يكتب ملف التحقق بتاع Search Console |
| `key` | ينشئ ملف مفتاح IndexNow |
| `submit` | يبعت روابطك لـ IndexNow وكل المحركات المشتركة |
| `action` | يركب GitHub Action يبعت تلقائي مع كل push |

## البداية السريعة (GitHub Pages)

```bash
# جوه فولدر موقعك (اللي فيه index.html)
python seo_launch.py fix --base-url https://YOU.github.io/YOUR-SITE/
python seo_launch.py sitemap --base-url https://YOU.github.io/YOUR-SITE/
python seo_launch.py robots --base-url https://YOU.github.io/YOUR-SITE/
python seo_launch.py key --base-url https://YOU.github.io/YOUR-SITE/
git add -A && git commit -m "seo-launch" && git push

# بعد ما ملف المفتاح يبقى شغال على الموقع:
python seo_launch.py submit --base-url https://YOU.github.io/YOUR-SITE/
```

وبعدها ركب الـ Action عشان كل push جديد يتبعت لوحده:

```bash
python seo_launch.py action
```

وارفع `.github/workflows/seo-launch.yml` وظبط متغيرين في إعدادات الريبو
(Settings > Secrets and variables > Actions > Variables):

- `SEO_BASE_URL` = رابط موقعك
- `SEO_SITE_DIR` = الفولدر اللي الموقع بينشر منه (`docs` أو سيبه فاضي لجذر الريبو)

## المتطلبات

بايثون 3.8 أو أحدث. ولا مكتبة، ولا تثبيت.

## الترخيص

MIT - شوف [LICENSE](LICENSE).
