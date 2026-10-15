# Talk naturally to Kadence

These are examples, not passwords. Common wording takes a fast local path;
unfamiliar phrasing goes through the reasoning model and the same real tools.
Kadence asks for a missing detail when she needs one. An answer that says an
action happened must come from the camera, tracker or local reminder store.

| You want | Examples |
|---|---|
| Identify what is visible | What's this? • What am I holding? • What's in my hand? • What do I have in my hand? • What have I got here? • Can you see this? • Identify this • Describe this • Any idea what I've got here? • Could you inspect this for me? |
| Colour or detail | What colour is this? • What color is the bottle? • Is the bottle blue? • What shape is that? • Read this • Read the label • Scan this • Can you make out what I'm holding? |
| Fresh scene or follow-up | What can you see? • What are you looking at? • What's on my desk? • Where is the bottle? • Is it still there? • Can you see the bottle? • Take a look at my hand |
| Follow an object | Track the bottle • Follow this mug • Keep track of the red ball • Could you track that for me? • Would you mind following the bottle? • I'd like you to keep that bottle centred as I move it |
| Watch for an event | Watch the bottle • Monitor the mug for movement • Tell me if it gets moved • Let me know when the bottle disappears • Notify me when the bottle moves • Remind me when the blue bottle moves • Stop watching |
| Create a reminder | Remind me to check the print in twenty minutes • Set a reminder to order filament tomorrow at noon • Set me a reminder • Create a reminder for me • I need a reminder • I'd like a reminder • Don't let me forget • Make sure I don't forget • Give me a prod in twenty minutes to check the print |
| Different word order | Remind me at 7 pm to check the print • In twenty minutes remind me to check the print • Tomorrow remind me I need to order filament • Nudge me in twenty minutes to check the print • Send me a nudge tomorrow at noon to order filament |
| Timer | Set a timer for ten minutes • Start a ten-minute timer • Start a timer for half an hour called check the print • Begin a timer for an hour and a half |
| Answer or correct | Nine am • In the morning • Make it nine instead • Actually, make that 7 pm instead • Move the print reminder to tomorrow at 8 pm • Push back the filament reminder to tomorrow at noon |
| Manage reminders | Read my reminders • What reminders do I have? • Do I have any reminders? • Show me my reminders • Cancel reminder two • Delete the filament reminder • Cancel that reminder • Snooze that for ten minutes |
| Existing local tools | What time is it? • What's the date? • Remember that… • Make a note that… • Read my notes • Add… to my list • What's on my list? • Calculate… • Convert… |

Relative times use the PC clock and configured timezone (Europe/London by
default). Named dates, tomorrow, the day after tomorrow, weekdays, am/pm, noon,
midnight, half/quarter hours and combined durations are resolved locally.
“At seven” asks am or pm. “Tomorrow” asks what time. Corrections to the last
handled reminder remain available for two minutes and update that same record.
A task name matching multiple reminders asks which one; it never guesses.

Camera watches currently run for up to fifteen minutes and produce one alert
for sustained movement or loss of sight. A covered object is reported as lost
from view, not stolen. Stop, privacy or disconnect cancels the watch.
“When I get home”, printer-finished events and repeating schedules do not yet
have supported triggers; Kadence says so and can offer a timed reminder.
She does not create a pretend background task.

Recognition depends on the actual microphone transcript and, for unfamiliar
wording, the selected reasoning model. Regression tests prove phrase routing,
tool execution and clarification; they do not claim every possible utterance
or every live vision answer will be correct.
