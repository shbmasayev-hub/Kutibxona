# Kutibxona Telegram bot

Telegram bot kitoblarni PDF ko‘rinishida, audiokitoblarni esa Telegram audio
pleyerida yuboradi. Interfeys o‘zbek va rus tillarida ishlaydi.

## Docker orqali ishga tushirish

1. BotFather’dan bot tokenini oling va Telegram’da `/myid` yuborib o‘z
   foydalanuvchi ID’ingizni aniqlang.
2. `.env.example` faylidan `.env` nusxa yarating va quyidagilarni kiriting:
   - `TELEGRAM_BOT_TOKEN` — bot tokeni.
   - `TELEGRAM_ADMIN_IDS` — fayl yuklashga ruxsat berilgan ID’lar, vergul bilan
     ajratilgan.
3. Ishga tushiring:

   ```sh
   docker compose up -d --build
   docker compose logs -f bot
   ```

`books_data` Docker volume’i PDF va audio yuklamalarini konteyner qayta
ishga tushganda ham saqlaydi. Mavjud `books/uploads/` va `books/audio/`
fayllari Git’dan ataylab chiqarilgan; yangi serverga o‘tganda ularni volume’ga
alohida ko‘chiring. 20 MB gacha bo‘lgan fayllarni admin akkauntidan botga
qayta yuklash ham mumkin. Docker volume’ni saqlash uchun
`docker compose down -v` buyrug‘ini ishlatmang.

Bot polling ishlatadi, shuning uchun bitta token bilan faqat bitta bot
jarayonini ishga tushiring. Aks holda Telegram `409 Conflict` qaytarishi
mumkin. Tokenni `.env` ichida saqlang; `.env` va service-account kalitlarini
Git’ga qo‘shmang. Bepul/oddiy hosting rejasida bot uxlab qolmasligi va media
yo‘qolmasligi uchun doimiy ishlaydigan jarayon hamda persistent disk kerak.

Telegram orqali yuklash faqat `TELEGRAM_ADMIN_IDS` ro‘yxatidagi adminlar uchun
ochiq; har bir fayl 20 MB gacha. Kitoblarni boshqalarga ulashishdan oldin
tarqatish huquqiga ega ekaningizni tekshiring.

## Telegram 3D App Launcher

Bot menyusidagi launcher Telegram ichida kitoblar, audiokitoblar, o‘qituvchi,
o‘quvchi va umumiy resurslar bo‘limlarini ochadi. Mini App sahifasi `webapp/`
papkasida; GitHub Pages’da `/webapp/` yo‘li orqali HTTPS’da taqdim etiladi.
Mavjud saytning bosh sahifasi root `index.html` bo‘lib qoladi.

Yoqish uchun:

1. O‘zgarishlarni `main` ga qo‘shing.
2. Repository Settings → Pages → Build and deployment → Source’da **GitHub
   Actions** ni tanlang (hozirgi Pages manbasi `main` branch).
3. `Deploy Kutibxona Pages` workflow’ini ishga tushiring yoki keyingi `main`
   yangilanishini kuting.
4. Bot ishlayotgan muhitda `TELEGRAM_WEBAPP_URL` ni
   `https://shbmasayev-hub.github.io/Kutibxona/webapp/` qilib belgilang va
   botni qayta ishga tushiring.

Bot menyusidagi “🚀 3D kutubxona” tugmasi `TELEGRAM_WEBAPP_URL` to‘g‘ri
sozlangandagina ko‘rinadi. Maxsus domen kerak emas.

## O‘quvchilar bo‘limi

Botda o‘quvchilar `Sinfni tanlash → Fanni tanlash` orqali 1–11-sinf
resurslariga o‘tadi. Har bir fan sahifasida mustaqil o‘qish va shu fanni
o‘rganish bo‘yicha tavsiya, shuningdek [ZiyoNET kutubxonasi](https://library.ziyonet.uz/),
[o‘zbekcha audiokitoblar](https://audio.ziyonet.uz/) va
[ta’lim savol-javoblari](https://ask.ziyonet.uz/) havolalari bor.
Mualliflik huquqi aniq bo‘lmagan fayllar bot serveriga ko‘chirib olinmaydi.

## O‘qituvchilar bo‘limi

Bo‘limda darsni rejalash, darajaga mos topshiriqlar tayyorlash hamda
formativ baholash bo‘yicha bot ichida yozilgan amaliy metodik tavsiyalar va
[ZiyoNET kutubxonasi](https://library.ziyonet.uz/), [savol-javob xizmati](https://ask.ziyonet.uz/)
hamda [foydali saytlar katalogi](https://sites.ziyonet.uz/) havolalari mavjud.
“Darsni rejalash” bo‘limida 1–4-sinflar va 5–11-sinflar uchun alohida PDF
qo‘llanmalar mavjud. Har biri o‘z sinf bosqichiga mos yondashuvlar va
namunaviy darslarni, shuningdek baholash hamda foydalanishga tayyor reja
qolipini o‘z ichiga oladi. Tashqi saytlardagi materiallar botga nusxalanmaydi.
