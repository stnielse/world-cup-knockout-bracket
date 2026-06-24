Background: I am a professional software engineer most familiar with django frameworks.

Project goal: I want to build a simple but modern website for people to run a group-based bracket competition for the knockout rounds of the FIFA world cup. I will be the sole admin user with the ability to adjust the backing database and framework. I want users to be able to setup a free and minimal account, with the ability to either start a new group or join a group another user setup using a specific key. Once a group is setup, each user will have the ability to predict the winners of each match in the opening round, which will automatically populate the corresponding bracket places in the following round, so on and so forth. Users should be able to update their picks until one hour before the relevant match starts, at which their picks will become frozen. Users should be awarded points for correct predictions and within each group there should be a live leaderboard.

Soccer info: The knockout rounds are as follows, Round of 32: June 28 – July 3. Round of 16: July 4 – July 7. Quarterfinals: July 9 – July 11. Semifinals: July 14 – July 15. Third Place Playoff: July 18. Final: July 19. The exact layout of the matchups in the round of 32 will not be known until June 27.

Database: I initially wanted to use api-football.com, hence the api-key in my .env.example, for pulling the relevant data in but their free plan does not support the ongoing world cup so I'm leaning towards manually updating the underlying data that will populate users' groups myself. We can probably disregard api-football.com

Current project layout: I have it setup as a python venv with a Makefile and requirements.txt. flake8 and black are prepackaged to be used in the future for python linting and formatting, installed inside the makefile.

Questions/considerations:
    - Which framework to use? I'm a django native but open to others if it isn't the best fit for this project.
    - Which database to use? I'm used to postgres with redis cache combo, but same story as above.
    - Domain name and setup? My professional work involves working on legacy codebases so I'm not too savvy on the process of setting up a from-scratch website. I WANT TO AVOID PAYING FOR ANYTHING IF AT ALL POSSIBLE. Are there free options? The people that will be using this bracket app will not be tech savvy so I can't just share the repo and say "spin up a localhost".

Let's work together to come up with a plan forward for the above.
