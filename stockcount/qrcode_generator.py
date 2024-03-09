import qrcode
import qrcode.image.svg


def main():
    data = "stockcount.centraarchy.com"

    factory = qrcode.image.svg.SvgImage

    img = qrcode.make(data, image_factory=factory)
    img.save("./static/img/QRCode.svg")


if __name__ == "__main__":
    main()
