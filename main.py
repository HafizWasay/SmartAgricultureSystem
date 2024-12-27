import RPi.GPIO as GPIO
import time
import board
import busio
from adafruit_ads1x15.ads1115 import ADS1115
from adafruit_ads1x15.analog_in import AnalogIn

INFLUXDB_TOKEN="GbV71pmPTQ7-dDUW9eNFzSlfat4f7LCoCTm-9dDKczIDKUyZGo_-3-x-nV92pKQKO8dy010z80MZcBpw6WlNiA=="
import os, time
from influxdb_client_3 import InfluxDBClient3, Point

token = INFLUXDB_TOKEN
org = "SHU"
host = "https://us-east-1-1.aws.cloud2.influxdata.com"
database="SAS"

client = InfluxDBClient3(host=host, token=token, org=org)


def write_to_db(field, value):
  point = (
    Point("SAS")
    .field(field, value)
  )
  client.write(database=database, record=point)
  time.sleep(1) # separate points by 1 second

# GPIO Pin Configuration
RELAY_PIN = 17  # GPIO pin connected to relay's IN pin
MOISTURE_SENSOR_PIN = 27  # GPIO pin connected to soil sensor's DO pin
WATER_LEVEL_SENSOR_PIN = 23  # GPIO pin connected to water level sensor's + terminal

# Initialize GPIO
GPIO.setmode(GPIO.BCM)
GPIO.setup(RELAY_PIN, GPIO.OUT)
GPIO.setup(MOISTURE_SENSOR_PIN, GPIO.IN)
GPIO.setup(WATER_LEVEL_SENSOR_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)  # Enable internal pull-up resistor

# Initialize I2C and ADS1115
i2c = busio.I2C(board.SCL, board.SDA)
ads = ADS1115(i2c)

# Configure gain to match the sensor's voltage range
ads.gain = 1

VOLTAGE_AT_PH_7 = 2.5  # Voltage corresponding to pH 7
SENSITIVITY = 0.18  # Change in voltage per pH unit (in volts)

CLEAR_WATER_VOLTAGE = 4.2  # Voltage for clear water
MAX_TURBIDITY_VOLTAGE = 2.5  # Voltage for highly turbid water

# Function to start the water pump
def start_pump():
    GPIO.output(RELAY_PIN, GPIO.HIGH)  # Activate relay
    print("Pump started...")
    time.sleep(5)  # Run pump for 5 seconds
    GPIO.output(RELAY_PIN, GPIO.LOW)  # Deactivate relay
    print("Pump stopped.")

# Function to convert voltage to pH
def get_ph(voltage):
    return 7 - ((voltage - VOLTAGE_AT_PH_7) / SENSITIVITY)

def average_voltage(channel, num_samples=10):
    total_voltage = sum(channel.voltage for _ in range(num_samples))
    return total_voltage / num_samples

def calculate_ntu(voltage):
    # Linear mapping from voltage to NTU
    max_ntu = 100  # Adjust based on sensor datasheet or calibration
    ntu = (CLEAR_WATER_VOLTAGE - voltage) * max_ntu / (CLEAR_WATER_VOLTAGE - MAX_TURBIDITY_VOLTAGE)
    return max(0, ntu)

try:
    while True:

        # Water pH Sensor Reading
        ph_channel = AnalogIn(ads, 0)  # Assuming pH sensor is connected to A0
        ph_voltage = average_voltage(ph_channel)
        ph_value = get_ph(ph_voltage) 
        print(f"pH Sensor -> Voltage: {ph_voltage:.2f} V, pH Value: {ph_value:.2f}")

        # Turbidity Sensor Reading
        turbidity_channel = AnalogIn(ads, 1)  # Assuming turbidity sensor is connected to A1
        turbidity_voltage = turbidity_channel.voltage
        ntu_value = calculate_ntu(turbidity_voltage)
        if ntu_value <= 1:
            ntu = "Clear Water"
        elif ntu_value <= 5:
            ntu = "Slightly Cloudy"
        elif ntu_value <= 50:
            ntu = "Moderately Turbid"
        elif ntu_value <= 100:
            ntu = "Very Turbid"
        else:
            ntu = "Highly Turbid" 
        print("Turbidity Sensor", ntu_value)

        #tank status
        tank_empty = GPIO.input(WATER_LEVEL_SENSOR_PIN) == GPIO.LOW
        
        # Moisture Sensor Reading
        soil_dry = GPIO.input(MOISTURE_SENSOR_PIN)  # HIGH means dry, LOW means wet
        if soil_dry:
            soil_val = 'Dry'
            # Water Level Sensor Reading
            
            if tank_empty:
                tank_val = 'Empty'
                print("Soil is Dry but Water Tank is empty!")
            else:
                tank_val = 'Full'
                print("Water Tank is full!")
                print("Soil is dry and tank is full. Starting the pump...")
                start_pump()
        else:
            soil_val = 'Moist'
            print("Soil is moist. No action needed.")

        #  Writing in db
        write_to_db("PH", ph_value)
        write_to_db("Turbide", ntu)
        write_to_db("Soil Moist", soil_val)
        write_to_db("Tank Status", tank_val)
        
        # Delay before next cycle
        time.sleep(2)  # Check every 2 seconds

except KeyboardInterrupt:
    print("Exiting program.")

finally:
    GPIO.cleanup()