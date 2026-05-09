================================================================
  Highway Rasoi POS  —  Test Build for Windows
================================================================

WHAT YOU NEED
-------------
Python 3.x installed on your machine.
   Download: https://www.python.org/downloads/
   IMPORTANT: during install, tick "Add Python to PATH".


HOW TO START
------------
Double-click  >>>  "Highway Rasoi POS.bat"  <<<

That's it. The first launch will:
  - install the required packages quietly (Flask, etc.)
  - start the server on http://127.0.0.1:5003
  - automatically open the login page in your browser


LOGIN
-----
Biller (the cashier / staff login):
  ID         BILLER001
  Password   Pass@1234

Admin (manage billers + view audit logs at /admin/login):
  ID         POSADMIN2024
  Password   Adm!nX9@Secure


OPTIONAL — A NICE DESKTOP ICON
------------------------------
A .bat file shows a generic icon by default. To get a proper
Highway Rasoi POS icon on your Desktop:

  Double-click  >>>  "Create Desktop Shortcut.bat"  <<<

This creates a "Highway Rasoi POS" shortcut on your Desktop that
uses the bundled app-icon.ico. From then on you can just open
the platform from the Desktop.


THIS IS A FRESH SETUP
---------------------
The database starts empty — no menu items, tables, inventory,
rooms, customers, suppliers, or bookings. Add your own from:

  - Menu      → /menu          (categories + items)
  - Terminal  → /              (add tables here)
  - Inventory → /inventory     (stock + suppliers + purchases)
  - Hotel     → /hotel         (rooms + bookings calendar)
  - Customers → /customers
  - Settings  → /settings      (restaurant name, tax, currency, etc.)


TO STOP THE SERVER
------------------
Just close the black command-prompt window, or press Ctrl+C in it.


ACCESSING FROM A PHONE / TABLET ON THE SAME WI-FI
-------------------------------------------------
While the server is running, find your PC's local IP (run
"ipconfig" in the command prompt — look for "IPv4 Address",
typically 192.168.x.x). Then on your phone, open:

  http://YOUR-PC-IP:5003/login

(Make sure your firewall allows incoming connections on port 5003.)


TROUBLESHOOTING
---------------
- "Python is not installed or not on PATH"
    Reinstall Python 3 and tick the "Add Python to PATH" checkbox
    on the very first install screen.

- The browser doesn't auto-open
    Manually open http://127.0.0.1:5003/login in any browser.

- "Address already in use" / port 5003 busy
    Another instance is already running, OR something else has
    grabbed port 5003. Close other terminal windows and try again.

================================================================
