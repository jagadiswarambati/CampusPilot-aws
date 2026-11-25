# 90-second demo script

Goal: show a real problem, a working AWS solution with several services, and the polish of the product,
in 60 to 90 seconds.

## Before recording

- Deploy with `./scripts/deploy.sh` and open the **live Amplify URL**, not localhost, in a fresh incognito window.
- Choose **Lunch hour** in the campus clock (top right). It makes the canteen and print shops busy, which shows the agent at its best.
- Click through the app once beforehand so the Lambda is warm, then reload.
- Record on a laptop at 110% zoom. If you also want a phone clip, show the sidebar drawer for two seconds.
- Say once, briefly, that campus data is sample data and orders are simulated.

## Script

| Time | On screen | Say |
|---|---|---|
| 0:00–0:08 | Dashboard: the "Next up" board, stats and heat strip | "Students lose time to small uncertainties: is there a library seat, how long is the print queue, will I make it to class? CampusPilot answers all of it, on AWS." |
| 0:08–0:35 | Break Planner: click the first example, press **Plan my break**; let the agent steps appear, then show the verdict and break bar | "I describe my break in plain English. The agent checks live print queues and the canteen, simulates every combination, and shows me exactly why. This plan fits with minutes to spare. The numbers come from tested code, not an AI guess." Click **Place simulated orders**. |
| 0:35–0:55 | Library: choose a slot, pick a seat, **Book this seat**, show the pass | "Library seats work like cinema seats. Bookings use a DynamoDB transaction, so two students can never get the same seat." |
| 0:55–1:10 | Print shops, then Canteen (add two items, place the order) | "The print agent shows rush and recommends the faster shop. In the canteen I order ahead and get a pickup token." |
| 1:10–1:20 | Back to the Dashboard: the board now lists your seat, print job and food order | "Everything lands on one board, with live status." |
| 1:20–1:30 | AWS architecture page, press **Run live check** | "Amplify, API Gateway, Lambda, DynamoDB, and optional Bedrock, all serverless. CampusPilot: your campus, one app." |

If you enabled Bedrock for the video, point at "Understood with Amazon Bedrock". If it says "built-in rules",
do not claim Bedrock.

## Do not claim

- Real campus data, real shop or canteen integration, real payments, or user statistics you did not collect.
- Bedrock, if the planner says "built-in rules".
- That attendance check-in verifies location. It is simulated.

## Submission checklist

- [ ] Builder Center profile and alias ready, SheerID verification done
- [ ] Live link works in an incognito window and on a phone
- [ ] README placeholders replaced (live URL, video link, alias) and screenshots added
- [ ] Video is 60–90 seconds and its link opens without signing in
- [ ] Form submitted at <https://techfest.org/aws-shipit-challenge> before 27 November 2026
- [ ] Screenshot of the confirmation page saved as proof
- [ ] Stack left running until results are announced, then `./scripts/destroy.sh`
