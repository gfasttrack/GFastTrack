/*
  SafeTrack sample for one ESP32.

  This board POSTs a location report to one device URL.
  Flask receives it in backend/app.py, function ingest().

  Change WIFI_SSID, WIFI_PASSWORD, and SERVER before you flash.
  SERVER must be this computer's network address, not 127.0.0.1.
  Example: http://10.120.17.47:5000/api/ingest/ST-9F951F
  The last part, ST-9F951F, is the Device ID from the admin site.
*/

#include <WiFi.h>
#include <HTTPClient.h>

const char* WIFI_SSID = "your-wifi-name";
const char* WIFI_PASSWORD = "your-wifi-password";

// One URL, one device. Copy it from the admin Devices page.
const char* SERVER = "http://10.120.17.47:5000/api/ingest/ST-9F951F";

void setup() {
  Serial.begin(115200);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("Connecting to Wi-Fi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();
  Serial.print("ESP32 address: ");
  Serial.println(WiFi.localIP());
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    delay(2000);
    return;
  }

  // These numbers would come from the GPS module, battery pin, and SOS button.
  float lat = 5.5600;
  float lng = -0.2050;
  float speed = 4;
  int battery = 80;
  float temperature = 32;
  const char* signal = "Good";
  bool sos = false;

  // The body is JSON text. Flask reads these same names: lat, lng, speed, battery, temperature, signal, sos.
  String body = "{";
  body += "\"lat\":" + String(lat, 6) + ",";
  body += "\"lng\":" + String(lng, 6) + ",";
  body += "\"speed\":" + String(speed, 1) + ",";
  body += "\"battery\":" + String(battery) + ",";
  body += "\"temperature\":" + String(temperature, 1) + ",";
  body += "\"signal\":\"" + String(signal) + "\",";
  body += "\"sos\":" + String(sos ? "true" : "false");
  body += "}";

  HTTPClient http;
  http.begin(SERVER);
  http.addHeader("Content-Type", "application/json");

  // POST sends the body to SERVER. This is the request.
  int status = http.POST(body);
  String reply = http.getString();
  http.end();

  Serial.print("POST ");
  Serial.println(SERVER);
  Serial.println(body);
  Serial.print("Server answered ");
  Serial.print(status);
  Serial.print(" ");
  Serial.println(reply);

  delay(5000);
}
