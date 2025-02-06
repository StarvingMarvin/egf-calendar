# EGF Calendar Scraper

This simple script scrapes [EGF's calendar](https://www.eurogofed.org/calendar/)
page and converts it's output to ical and rss files.

The script is "fairly self-explanatory" (read: completely comment free),
takes no parameters (values are hardcoded) and does no error handling.

You can check (and use) outputs of this script: 
[RSS](http://li1418-60.members.linode.com/egf-calendar.rss)
and [iCal](http://li1418-60.members.linode.com/egf-calendar.ics),
files are regenerated ~twice a day.
You can also tweak and run the script yourself:
the only two dependencies are `requests` and `beautifulsoup4`.

If you are someone who can make this functionality a part of EGF's website,
feel free to use this code or to contact me to help you implement it.

