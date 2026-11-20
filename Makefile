VERSION := 0.1.0

.PHONY: icons deb rpm flatpak appimage install uninstall clean

icons:
	python3 scripts/make_icons.py

deb:
	bash scripts/build-deb.sh

rpm:
	bash scripts/build-rpm.sh

flatpak:
	bash scripts/build-flatpak.sh

appimage:
	bash scripts/build-appimage.sh

install:
	./install.sh

uninstall:
	./uninstall.sh

clean:
	rm -rf build
