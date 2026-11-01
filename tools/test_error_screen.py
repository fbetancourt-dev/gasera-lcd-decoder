#!/usr/bin/env python3
"""
Automated Test for Pegasus Gasera LCD Decoder - OCR Screen Guard
Verifies that when $ or Lt markers are missing (e.g. error screens like
'NO SURTIR ERR 0100 UNIDAD 0004', menu states, or transitions), the clean text display
automatically blanks out to prevent displaying stale sale or volume numbers.
"""

import os
import sys
import time

def test_screen_guard(host="127.0.0.1", port=8081):
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
    except ImportError:
        print("Selenium not installed. Run: pip install selenium")
        return 1

    url = f"http://{host}:{port}/lcd_decoder_light.html"
    print(f"Connecting to decoder at {url}...")
    
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Chrome(options=opts)

    try:
        driver.get(url)
        time.sleep(2.0)

        # 1. Check with valid markers present
        status_valid = driver.execute_script("""
            return {
                screenGuardActive: state.screenGuardActive,
                cleanRows: state.cleanRows,
                c1Hidden: $('cleanRowContainer1').hidden,
                c2Hidden: $('cleanRowContainer2').hidden,
                row1Text: $('cleanRow1').textContent,
                row2Text: $('cleanRow2').textContent
            };
        """)
        print("1. Normal Sale State (with $ & Lt markers):")
        print(f"   screenGuardActive: {status_valid['screenGuardActive']}")
        print(f"   cleanRows: {status_valid['cleanRows']}")
        print(f"   containers hidden: c1={status_valid['c1Hidden']}, c2={status_valid['c2Hidden']}")

        # 2. Simulate error screen: Zero out the left 20 columns where $ and Lt reside
        driver.execute_script("""
            stopLiveCapture();
            for (let page = 0; page < 8; page++) {
                for (let x = 0; x < 20; x++) {
                    state.framebuffer[page * state.meta.controllerWidth + x] = 0;
                }
            }
            draw();
        """)
        time.sleep(0.5)

        status_error = driver.execute_script("""
            return {
                screenGuardActive: state.screenGuardActive,
                cleanRows: state.cleanRows,
                c1Hidden: $('cleanRowContainer1').hidden,
                c2Hidden: $('cleanRowContainer2').hidden,
                row1Text: $('cleanRow1').textContent,
                row2Text: $('cleanRow2').textContent
            };
        """)
        print("\n2. Error Screen State (zeroed markers / NO SURTIR ERR 0100):")
        print(f"   screenGuardActive: {status_error['screenGuardActive']}")
        print(f"   cleanRows: {status_error['cleanRows']}")
        print(f"   containers hidden: c1={status_error['c1Hidden']}, c2={status_error['c2Hidden']}")
        print(f"   row text: row1='{status_error['row1Text']}', row2='{status_error['row2Text']}'")

        assert not status_error['screenGuardActive'], "Screen guard should NOT be active when markers are missing"
        assert status_error['c1Hidden'] and status_error['c2Hidden'], "Clean display containers must be hidden"
        assert status_error['row1Text'] == '' and status_error['row2Text'] == '', "Clean display rows must be empty"

        print("\n✅ PASSED: Screen guard successfully blanks clean display when markers disappear.")
        return 0

    except Exception as e:
        print(f"\n❌ FAILED: {e}")
        return 1
    finally:
        driver.quit()

if __name__ == "__main__":
    sys.exit(test_screen_guard())
