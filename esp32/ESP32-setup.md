# SafeTrack ESP32 setup

Give this sheet to the person writing the ESP32 firmware. The phone app does not talk to the board directly. The board sends a location report to the SafeTrack server. The app reads that report.

A working sample is in `esp32/ASP32/ASP32.ino`. The server receives it in `backend/app.py`, function `ingest()`.

## 1. Create the device first

1. Open the admin site: `http://<server>/admin`
2. Sign in (local test: username `admin`, password `admin`).
3. Click **Create device**. The site generates a Device ID, for example `ST-9F951F`.
4. Copy the ingest URL shown next to that ID.

The URL looks like this:

```text
http://10.120.17.47:5000/api/ingest/ST-9F951F
```

The last part is the Device ID. One URL belongs to one device. Do not share one URL across two boards.

The board must use the computer’s network address, such as `10.120.17.47`. Do not put `127.0.0.1` or `localhost` in the ESP32 code. Those names mean the board itself, so the report never reaches the server.

The phone, the computer running SafeTrack, and the ESP32 must be on the same Wi-Fi while you are testing on this computer.

After a user creates an account in the app, they enter this same Device ID. Until that ID exists (created in admin, or entered on an account), the server answers `404`.

## 2. What the board sends

Method: `POST`  
Header: `Content-Type: application/json`  
Body: one JSON object.

`lat` and `lng` are required. The other fields are optional. If you leave one out, the server keeps the previous value.

```json
{
  "lat": 5.560000,
  "lng": -0.205000,
  "speed": 4.0,
  "battery": 80,
  "temperature": 32.0,
  "signal": "Good",
  "sos": false
}
```

| JSON name | Type | Meaning in the app |
| --- | --- | --- |
| `lat` | number | Latitude. From -90 to 90. |
| `lng` | number | Longitude. From -180 to 180. |
| `speed` | number | Speed in km/h. The app shows this as “5 km/h”. |
| `battery` | number | Battery percent, 0 to 100. |
| `temperature` | number | Temperature in °C. The app shows this as “32°C”. |
| `signal` | text | Short signal label, for example `Good`, `Fair`, or `Weak`. At most 40 characters. |
| `sos` | true or false | `true` raises the SOS alert in the app. Send `false` when the alert is clear. |
| `address` | text | Optional place name. If you omit it, the server looks up the place from `lat` and `lng`. |

Numbers must be JSON numbers, not text. `sos` must be `true` or `false`, not `1` or `"yes"`.

Send a report about every 5 seconds while the device is on. The app treats the device as online when a report arrives, and offline if none arrives for 3 minutes after the first fix.

## 3. What the server answers

Success:

```json
{"ok": true}
```

HTTP status `200`.

If something is wrong, the body looks like this:

```json
{"error": "Send lat and lng."}
```

| HTTP status | Usual reason |
| --- | --- |
| 200 | Report saved. |
| 400 | `lat` or `lng` is missing or outside the allowed range. |
| 401 | `X-Device-Key` does not match. Only when the server has `DEVICE_INGEST_KEY` set. Leave this header off for local testing. |
| 404 | That Device ID does not exist yet. Create it in admin, or have the user add it on their account. |

## 4. Play Beep

When someone taps **Play Beep** in the app, the server stores a command for that Device ID. The board should ask for commands on its own schedule, for example every few seconds:

```text
GET http://10.120.17.47:5000/api/ingest/ST-9F951F/commands
```

Answer when a beep is waiting:

```json
{"commands": ["beep"]}
```

Answer when nothing is waiting:

```json
{"commands": []}
```

Each command is delivered once. After this response, that beep is cleared. If `commands` contains `"beep"`, sound the buzzer.

## 5. Minimal ESP32 shape

```cpp
#include <WiFi.h>
#include <HTTPClient.h>

const char* WIFI_SSID = "your-wifi-name";
const char* WIFI_PASSWORD = "your-wifi-password";
const char* SERVER = "http://10.120.17.47:5000/api/ingest/ST-9F951F";

// Replace the numbers with the GPS, battery, and SOS button readings.
String report(float lat, float lng, float speed, int battery, float temperature, const char* signal, bool sos) {
  String body = "{";
  body += "\"lat\":" + String(lat, 6) + ",";
  body += "\"lng\":" + String(lng, 6) + ",";
  body += "\"speed\":" + String(speed, 1) + ",";
  body += "\"battery\":" + String(battery) + ",";
  body += "\"temperature\":" + String(temperature, 1) + ",";
  body += "\"signal\":\"" + String(signal) + "\",";
  body += "\"sos\":" + String(sos ? "true" : "false");
  body += "}";
  return body;
}

void sendReport(String body) {
  HTTPClient http;
  http.begin(SERVER);
  http.addHeader("Content-Type", "application/json");
  int status = http.POST(body);
  http.end();
  // status 200 and {"ok": true} means the app can show this fix.
}
```

Change `WIFI_SSID`, `WIFI_PASSWORD`, and `SERVER` before flashing. `SERVER` must be the URL copied from the admin Devices page for that exact board.
