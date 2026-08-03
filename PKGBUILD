pkgname=ropro-bypass
pkgver=0.1.0
pkgrel=5
pkgdesc='Apply RoPro bypasses in place'
arch=('any')
license=('MIT')
depends=('python>=3.9')
provides=('ropro-client-override')
conflicts=('ropro-client-override')
replaces=('ropro-client-override')
url='https://github.com/Carpenter2149/ropro-bypass'
source=()
sha256sums=()

check() {
  cd "$startdir"
  python -B patch_ropro.py --help >/dev/null
  python -B -m unittest discover -s tests -v
  sha256sum -c MANIFEST.sha256
}

package() {
  cd "$startdir"

  install -Dm755 patch_ropro.py "$pkgdir/usr/lib/$pkgname/patch_ropro.py"
  install -d "$pkgdir/usr/lib/$pkgname/audits"
  install -m644 audits/*.json "$pkgdir/usr/lib/$pkgname/audits/"
  install -Dm644 LICENSE "$pkgdir/usr/share/licenses/$pkgname/LICENSE"
  install -Dm644 README.md "$pkgdir/usr/share/doc/$pkgname/README.md"
  install -d "$pkgdir/usr/bin"
  ln -s "../lib/$pkgname/patch_ropro.py" "$pkgdir/usr/bin/ropro-bypass"
}
