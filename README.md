# LanDrop

Chat dan kirim file antar laptop Windows di jaringan yang sama (Wi-Fi/LAN), mirip AirDrop / Quick Share.

## Install di setiap laptop
1. Salin `dist\LanDrop.exe` ke laptop (sekali saja: lewat flashdisk, email, atau Google Drive).
2. Klik dua kali `LanDrop.exe` → pilih **Yes** untuk install.
   - Jika muncul **"Windows protected your PC"** (SmartScreen): klik **More info → Run anyway** (EXE ini belum ditandatangani digital).
   - Jika muncul **Windows Firewall**: centang **Private networks** lalu **Allow access**. Tanpa ini laptop lain tidak bisa mengirim ke laptop ini.
3. Selesai. Shortcut ada di Desktop & Start Menu, dan LanDrop otomatis jalan di belakang saat Windows menyala.

Setelah laptop baru ter-install, selanjutnya cukup kirim `LanDrop.exe` versi baru lewat LanDrop sendiri.

## Pemakaian
- Laptop lain yang membuka LanDrop muncul otomatis di kiri (titik hijau = online).
- **Teks**: ketik lalu Enter. Klik **Salin** pada pesan untuk menyalin ke clipboard.
- **Gambar/screenshot**: tekan **Ctrl+V** di jendela chat (misalnya setelah Win+Shift+S).
- **File**: drag & drop ke jendela chat, atau tombol **+**. Ukuran tidak dibatasi.
- File diterima tersimpan di `Downloads\LanDrop` (bisa diubah di Pengaturan ⚙).
- Menutup jendela tidak mematikan LanDrop — tetap bisa menerima file. Untuk benar-benar keluar: ⚙ → **Keluar LanDrop**.

## Pengaturan penting (⚙)
- **Kunci pasangan**: isi kata kunci yang sama di semua laptop Anda. Laptop lain di jaringan (misal Wi-Fi kantor) yang tidak tahu kuncinya tidak bisa melihat atau mengirim ke Anda.
- **Tambah perangkat manual**: jika laptop tidak muncul otomatis (beberapa router/Wi-Fi kantor memblokir broadcast), masukkan IP laptop tujuan — IP-nya tertera di Pengaturan laptop tersebut.

## Jika perangkat tidak muncul
- Pastikan keduanya di jaringan yang sama dan network profile Windows = **Private** (Settings → Network → Properties).
- Pastikan LanDrop diizinkan di firewall (Windows Security → Firewall → Allow an app). Port yang dipakai: TCP 47801 dan UDP 47800.
- Wi-Fi tamu/publik sering memblokir komunikasi antar perangkat ("client isolation"); gunakan hotspot HP atau jaringan lain.

## Uninstall
Settings → Apps → **LanDrop** → Uninstall. File yang sudah diterima tidak dihapus.

## Catatan keamanan
Transfer tidak dienkripsi. Pakai di jaringan yang Anda percaya (rumah, hotspot sendiri). Kunci pasangan mencegah orang lain mengirim ke Anda, tetapi tidak menyembunyikan isi transfer dari orang yang menyadap jaringan.

## Build ulang dari source
Butuh Python 3.10+. Jalankan `build.bat` → hasil di `dist\LanDrop.exe`.
File: `landrop.py` (server, discovery, installer), `ui.html` (tampilan), `make_icon.py` (icon).
