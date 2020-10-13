import datetime
import tempfile
import glob
import itertools
import os
import qrcode
import qrcode.image.svg
import re
import requests
import serial
import subprocess
import sys
import json
from google.auth import jwt
from google.cloud import pubsub_v1
from pathlib import Path
from reportlab.graphics import renderPDF
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from svglib.svglib import svg2rlg

'''
##BEGIN_INFO##
##DFWV:v1.0.1-beta##
##MFWV:BC66NBR01A06##
##IMSI:333B59A574D5B##
##IMEI:315704EA8C445##
##STMUID:330044000151363039363936##
##SELF_TEST_RESULT:AOK##
##END_INFO##
'''

project_id = "safecility-prod"
topic_name = "device-ingestion"

service_account_info = json.load(open("/Users/tadmcallister/CN8680/SafecilityApplication/cn8680_production_tools/Resources/safecility-prod-c3b25e87e515.json"))
audience = "https://pubsub.googleapis.com/google.pubsub.v1.Subscriber"

credentials = jwt.Credentials.from_service_account_info(
    service_account_info, audience=audience
)
publisher_audience = "https://pubsub.googleapis.com/google.pubsub.v1.Publisher"
credentials_pub = credentials.with_claims(audience=publisher_audience)
publisher = pubsub_v1.PublisherClient(credentials=credentials_pub)

topic_path = publisher.topic_path(project_id, topic_name)

spinner = itertools.cycle(['|', '/', '--', "\\"])


class Label:
    pass


label = Label()

label.size = (89 * mm, 29 * mm)
label.icon = '/Users/tadmcallister/ProductionTools/QR_Generator/Resources/safecility_icon.svg'
label.ingest_api_url = 'https://app.safecility.com/ingestion/'
label.safecility_icon = '/Users/tadmcallister/ProductionTools/QR_Generator/Resources/safecility_icon.svg'


class Device:
    pass


device = Device()

device.dev_fwv = None
device.modem_fwv = None
device.imsi = None
device.imei = None
device.stm_uid = None


def publish_messsage(topic, message):
    data = message
    # Data must be a bytestring
    data = data.encode("utf-8")
    # When you publish a message, the client returns a future.
    future = publisher.publish(topic_path, data=data)
    return future.result()


def device_info_send():

    message = {
        'deviceType': 'DALI',
        'selfTestPass': True,
        'deviceId': {
            'imsi': device.imsi,
            'imei': device.imei,
            'uid': device.stm_uid,
            'dev_fw_v': device.dev_fwv,
            'modem_fw_v': device.modem_fwv
        },
        'deviceLocation': {
            'cellId': None,
            'locationAreaCode': None,
            'mobileCountryCode': None,
            'mobileNetworkCode': None
        }
    }

    try:
        json_message = json.dumps(message)
        print('Jsonified')
        print(json_message)
    except Exception as e:
        print('Failed to jsonify')
        print(e)

    try:
        result = publish_messsage(topic_name, json_message)
        print('Published message id: ' + result)
    except Exception as e:
        print('Failed to publish message')
        print(e)


def ser_clean(_ser):
    _ser.flush()
    _ser.close()


def get_ports():
    if sys.platform.startswith('win'):
        ports = ['COM%s' % (i + 1) for i in range(256)]
    elif sys.platform.startswith('linux'):
        ports = glob.glob('/dev/tty[A-Za-z]*')
    elif sys.platform.startswith('darwin'):
        ports = glob.glob('/dev/cu.*')
    else:
        raise EnvironmentError('ENV Unknown')

    return ports


def get_printers():
    avail_printers = str(subprocess.check_output("lpstat -p", shell=True).decode())

    if avail_printers.__contains__('enabled'):
        printer = str(subprocess.check_output("lpstat -p | awk '{print $2}'", shell=True).decode())
        print('\n', 'Printer found: ', str(printer))
        return str(printer)
    else:
        return 1


def get_opts(ports):
    print('\n', len(ports), ' Ports found\n')

    for item in ports:
        print('[', ports.index(item) + 1, ']', item)

    try:
        port_index = int(input("\n[ * ] Select TTL-USB from list:\n "))
    except ValueError:
        print("Invalid input\r\n")

    return ports[port_index - 1]


def get_label_count():
    count = None
    try:
        count = int(input("\nEnter label count:\n "))
    except ValueError as e:
        print('No Selection')

    if count is None:
        count = 1
    return count


def get_device_data(device_data, serial_port):
    try:
        ser = serial.Serial(str(serial_port), 115200)

        # Init Serial Connection
        try:
            ser.close()
            ser.open()
            print('Waiting for data...')
            try:
                while ser.inWaiting:
                    try:
                        line = str(ser.read_until(b'\r', None).decode('ISO-8859-1'))

                        # Exit on end string
                        if "##END_INFO##" not in line:

                            # Match O/P Vars
                            if "##DFWV" in line:
                                device_data.dev_fwv = re.search(r'(?<=\##DFWV:)(.*?)(?=\##)', str(line)).group(0)
                            if "##MFWV" in line:
                                device_data.modem_fwv = re.search(r'(?<=\##MFWV:)(.*?)(?=\##)', str(line)).group(0)
                            if "##IMSI" in line:
                                device_data.imsi = re.search(r'(?<=\##IMSI:)(.*?)(?=\##)', str(line)).group(0)
                            if "##IMEI" in line:
                                device_data.imei = re.search(r'(?<=\##IMEI:)(.*?)(?=\##)', str(line)).group(0)
                            if "##STMUID" in line:
                                device_data.stm_uid = re.search(r'(?<=\##STMUID:)(.*?)(?=\##)', str(line)).group(0)
                            if "##SELF_TEST_RESULT" in line:
                                device_data.test_res = re.search(r'(?<=\##SELF_TEST_RESULT:)(.*?)(?=\##)',
                                                                 str(line)).group(
                                    0)

                            # Wait until start string
                            if not "##BEGIN_INFO##" in line:
                                sys.stdout.write('\r' + 'Waiting for Device ' + str(next(spinner)))
                                sys.stdout.flush()

                            else:
                                sys.stdout.write('\r' + '** Start String Found **')
                                sys.stdout.flush()

                        else:
                            assert device_data.imsi is not None, "IMSI Not Found"
                            assert device_data.imei is not None, "IMEI Not Found"
                            assert device_data.stm_uid is not None, "STM_UID Not Found"

                            sys.stdout.write('\r' + '** Got Device Data **\n')
                            sys.stdout.flush()
                            break

                    except Exception as e:
                        print('Serial Line Read Error', e)
                        break

            except Exception as e:
                if e.args[0] == 6:
                    pass

        except serial.SerialException as e:
            print('TTL-USB Error: \n', e)

        except KeyboardInterrupt:
            print("Ctrl C - Exiting.")
            ser_clean(ser)
            os.exit(1)

        finally:
            print('Cleanup Serial...\n')
            ser_clean(ser)
            return device_data

    except serial.SerialException as e:
        print('Check TTL-USB connected & correct device selected: \n', e)


def generate_qr(url, data):
    print('Generating QR Code')
    qr = qrcode.QRCode(
        version=None,  # autosize
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=6,
        border=4
    )
    qr.add_data((str(url) + str(data)))
    qr.make(fit=True)
    qrcode_svg = qr.make_image(image_factory=qrcode.image.svg.SvgPathFillImage)
    svg_file = tempfile.NamedTemporaryFile()
    qrcode_svg.save(svg_file)  # store as an SVG file
    svg_file.flush()
    qrcode_rl = svg2rlg(svg_file.name)  # load SVG file as reportlab graphics
    svg_file.close()
    return qrcode_rl


def generate_pdf(device_data, output_filename):
    print('Generating PDF')
    ts = datetime.datetime.now().timestamp()
    qr_gen = generate_qr(label.ingest_api_url, device_data.imsi)  # generate qrcode
    c = canvas.Canvas(output_filename, pagesize=label.size)
    renderPDF.draw(qr_gen, c, 165, -2)  # render qr encoded join url

    icon = svg2rlg(label.safecility_icon)
    scaling_factor = 0.16
    icon.width = icon.minWidth() * scaling_factor  # scale icon to appropriate size
    icon.height = icon.height * scaling_factor
    icon.scale(scaling_factor, scaling_factor)
    renderPDF.draw(icon, c, 64, 22.5)  # render safecility logo

    # Draw info to canvas
    c.setStrokeColorRGB(0, 0, 0)
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica", 18)
    c.drawString(1 * mm, 24 * mm, str("Safecility™"))
    c.setFont("Helvetica", 6)
    c.drawString(1 * mm, 22 * mm, (str("www.safecility.com")))
    c.drawString(1 * mm, 16.5 * mm, (str("IMSI: ") + str(device_data.imsi)))
    c.drawString(1 * mm, 14.5 * mm, (str("IMEI: ") + str(device_data.imei)))
    c.drawString(1 * mm, 12.5 * mm, (str("UID: ") + str(device_data.stm_uid)))
    c.drawString(1 * mm, 10.5 * mm, (str("DFW: ") + str(device_data.dev_fwv)))
    c.drawString(1 * mm, 8.5 * mm, (str("MFW: ") + str(device_data.modem_fwv)))
    c.drawString(1 * mm, 6.5 * mm, (str("DT: ") + str(ts)))
    c.drawString(1 * mm, 0 * mm, (str(label.ingest_api_url) + str(device_data.imsi)))

    # Render page & save PDF
    c.showPage()
    c.save()

    return c


def post_ingest(params):
    try:
        r = requests.post(url=label.ingest_api_url, data=params)
        r.raise_for_status()
    except requests.exceptions.HTTPError as err:
        print('POST Request failed: ', err)


def print_label(filename, printer, num):
    print('Generating Label')

    lpr_str = "lpr -# {} -o portrait -o fit-to-page -o media=Custom.89x29mm -P {} {}"
    lpr_str = str(lpr_str.format(num, printer, filename)).replace('\r\n', '').replace('\r', '').replace('\n', '')

    print("START[", lpr_str, "]END")
    stat = os.system(lpr_str.strip())

    return stat


def main():
    # setup
    output_path = str(str(Path().resolve()) + '/Output/')
    print(output_path)

    welcome_msg = \
        "\n\t\
    ---------------------------------------------\n\t\
    || SafecilityDALI Device Provisioning Tool ||\n\t\
    ||-----------------------------------------||\n\t\
    ||* Ensure Valid Internet Connection       ||\n\t\
    ||* Ensure only 1x Printer connected to PC ||\n\t\
    ---------------------------------------------\n\
    ** Connect TTL-USB cable to modem UART & reset the device to begin **\n"

    print(welcome_msg)

    # get env info
    ports = get_ports()

    # get user input
    try:
        sel_port = get_opts(ports)
    except ValueError as e:
        print('No such port at index: {}\n{}'.format(sel_port, e))

    sel_print = get_printers()
    label_count = get_label_count()
    print('Selected: ', str(sel_port))
    print('Printing: ', label_count, ' labels')

    while True:
        # capture data
        try:
            d_data = get_device_data(device, sel_port)
        except Exception as e:
            print('Device data capture failed: {}'.format(e))

        filename = str(output_path + "label_%s.pdf" % d_data.imsi)

        if d_data.imsi is not None:

            # create PDF
            try:
                pdf_file = generate_pdf(d_data, filename)
            except Exception as e:
                print('Failed to create PDF: {}'.format(e))

            # publish device info to GCP pub/sub
            try:
                print("Publishing device info to Queue")
                device_info_send()

            except Exception as e:
                print('Failed to publish device info to Queue: {}'.format(e))

            if Path(filename).is_file():
                print("PDF exists: {}".format(Path(filename)))

                # print label
                try:
                    print_res = print_label(filename, sel_print, label_count)
                    if print_res is not 0:
                        print('Print Error: {}'.format(print_res))
                        raise FileNotFoundError

                except Exception as e:
                    print('Failed to print label. Ensure printer is connected: {}'.format(e))
            else:
                print("PDF does not exist")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Ctrl C - Stopping.")
        sys.exit(1)

    finally:
        sys.exit(1)
