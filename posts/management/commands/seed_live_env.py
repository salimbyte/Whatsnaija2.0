import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.auth import get_user_model

from posts.models import Post, Like, DisLike, PostImage, Bookmark
from comments.models import Comment, CommentLike, CommentDislike, CommentReaction
from stages.models import Stage, StageModerator, StageBan


class Command(BaseCommand):
    help = "Wipe posts/stages and seed a lively, Nigeria-themed dataset (synthetic content)."

    def add_arguments(self, parser):
        parser.add_argument("--wipe", action="store_true", help="Delete all posts, comments, reactions, and stages.")
        parser.add_argument("--force", action="store_true", help="Required with --wipe to confirm destructive delete.")
        parser.add_argument("--users", type=int, default=40, help="Number of additional users to create.")
        parser.add_argument("--per-stage", type=int, default=20, help="Minimum posts per stage.")
        parser.add_argument("--news-extra", type=int, default=10, help="Extra posts for the news stage.")
        parser.add_argument("--seed", type=int, default=42, help="Random seed for repeatable results.")
        parser.add_argument("--owner", type=str, default="salkt", help="Username for stage owner/admin.")

    def handle(self, *args, **options):
        if options["wipe"] and not options["force"]:
            self.stdout.write(self.style.ERROR("Refusing to wipe without --force."))
            return

        rng = random.Random(options["seed"])

        if options["wipe"]:
            self._wipe_data()
            self.stdout.write(self.style.SUCCESS("Wiped posts, comments, reactions, and stages."))

        User = get_user_model()
        owner = self._get_or_create_owner(User, options["owner"])

        users = self._ensure_users(User, owner, options["users"], rng)
        self.stdout.write(self.style.SUCCESS(f"Total users available: {len(users)}"))

        stages = self._create_stages(owner, rng)
        self.stdout.write(self.style.SUCCESS(f"Created {len(stages)} stages."))

        self._add_members(stages, users, owner, rng)
        self.stdout.write(self.style.SUCCESS("Added stage members."))

        posts = self._create_posts(stages, users, options["per_stage"], options["news_extra"], rng)
        self.stdout.write(self.style.SUCCESS(f"Created {len(posts)} posts."))

        comments = self._create_comments(posts, users, rng)
        self.stdout.write(self.style.SUCCESS(f"Created {len(comments)} comments."))

        self._create_post_reactions(posts, users, rng)
        self._create_comment_reactions(comments, users, rng)
        self.stdout.write(self.style.SUCCESS("Added likes/dislikes."))

        self.stdout.write(self.style.SUCCESS("Seeding complete."))

    def _wipe_data(self):
        CommentReaction.objects.all().delete()
        CommentLike.objects.all().delete()
        CommentDislike.objects.all().delete()
        Comment.objects.all().delete()
        Like.objects.all().delete()
        DisLike.objects.all().delete()
        PostImage.objects.all().delete()
        Bookmark.objects.all().delete()
        Post.objects.all().delete()
        StageModerator.objects.all().delete()
        StageBan.objects.all().delete()
        Stage.objects.all().delete()

    def _get_or_create_owner(self, User, username):
        owner, created = User.objects.get_or_create(
            username=username,
            defaults={
                "email": f"{username}@example.com",
                "is_staff": True,
            },
        )
        if created:
            owner.set_password("password123")
            owner.save()
        return owner

    def _ensure_users(self, User, owner, target_new, rng):
        first_names = [
            "Amina", "Chinedu", "Bola", "Tola", "Femi", "Uche", "Ife", "Sade", "Kunle",
            "Ada", "Zainab", "Hassan", "Tunde", "Kemi", "Ngozi", "Ibrahim", "Yemi",
            "Chisom", "Obinna", "Halima", "Segun", "Amaka", "Umar", "Bisi", "Emeka",
        ]
        last_names = [
            "Okoro", "Balogun", "Adeyemi", "Nwachukwu", "Ibrahim", "Ogunleye",
            "Eze", "Mohammed", "Okafor", "Yusuf", "Adebayo", "Ojo", "Abubakar",
            "Chukwu", "Ogundipe", "Olawale", "Giwa", "Iheanacho", "Omoregie",
        ]
        bios = [
            "Curious about policy, tech, and local news.",
            "Here for thoughtful debates and good faith takes.",
            "Sharing street-level updates and community views.",
            "Nollywood fan. Football on weekends.",
            "Learning, listening, and asking questions.",
        ]
        locations = [
            "Lagos", "Abuja", "Kano", "Kaduna", "Ibadan", "Enugu", "Port Harcourt",
            "Benin", "Calabar", "Jos", "Owerri", "Uyo", "Abeokuta", "Minna",
        ]

        users = list(User.objects.all())
        existing_usernames = {u.username for u in users}
        existing_usernames_lower = {u.username.lower() for u in users}

        def make_username():
            first = rng.choice(first_names)
            last = rng.choice(last_names)
            base = f"{first}{last}".lower()
            base = base.replace(" ", "")
            candidate = base
            counter = 1
            while candidate in existing_usernames or candidate.lower() in existing_usernames_lower:
                counter += 1
                candidate = f"{base}{counter}"
            existing_usernames.add(candidate)
            existing_usernames_lower.add(candidate.lower())
            return candidate, first, last

        created = 0
        for _ in range(target_new):
            username, first, last = make_username()
            user = User.objects.create_user(
                username=username,
                email=f"{username}@example.com",
                password="password123",
                first_name=first,
                last_name=last,
            )
            if hasattr(user, "profile"):
                user.profile.bio = rng.choice(bios)
                user.profile.location = rng.choice(locations)
                user.profile.save(update_fields=["bio", "location"])
            users.append(user)
            created += 1

        if owner not in users:
            users.append(owner)

        self.stdout.write(self.style.SUCCESS(f"Created {created} new users."))
        return users

    def _create_stages(self, owner, rng):
        stages_data = [
            ("news", "Nigeria News", "National and local news from across Nigeria.", "general"),
            ("politics", "Politics & Policy", "Governance, policy debates, and elections.", "general"),
            ("economy", "Economy & Markets", "Prices, jobs, FX, and macro trends.", "general"),
            ("business", "Business & Startups", "Companies, SMEs, and startup ecosystem.", "general"),
            ("tech", "Technology", "Apps, telecoms, AI, and innovation.", "tech"),
            ("sports", "Sports", "NPFL, Super Eagles, and grassroots sports.", "sports"),
            ("ent", "Entertainment", "Music, Nollywood, and pop culture.", "entertainment"),
            ("health", "Health", "Public health, hospitals, and wellness.", "interests"),
            ("education", "Education", "Schools, exams, and education policy.", "interests"),
            ("energy", "Energy", "Power, fuel, and sustainability.", "general"),
            ("culture", "Culture & Society", "Culture, lifestyle, and community life.", "creative"),
            ("transport", "Transport", "Roads, rail, and urban mobility.", "general"),
        ]

        created = []
        for name, title, desc, category in stages_data:
            stage, _ = Stage.objects.get_or_create(
                name=name,
                defaults={
                    "title": title,
                    "description": desc,
                    "admin": owner,
                    "category": category,
                    "is_active": True,
                },
            )
            created.append(stage)
        rng.shuffle(created)
        return created

    def _add_members(self, stages, users, owner, rng):
        for stage in stages:
            pool = [u for u in users if u.is_active]
            if owner not in pool:
                pool.append(owner)
            count = min(len(pool), rng.randint(12, max(12, min(120, len(pool)))))
            members = rng.sample(pool, count)
            if owner not in members:
                members.append(owner)
            stage.members.add(*members)
            stage.members_count = stage.members.count()
            stage.save(update_fields=["members_count"])

    def _create_posts(self, stages, users, per_stage, news_extra, rng):
        posts = []
        for stage in stages:
            count = per_stage + (news_extra if stage.name == "news" else 0)
            for _ in range(count):
                author = rng.choice(users)
                title = self._make_title(stage.name, rng)
                body = self._make_body(stage.name, rng)
                created_at = timezone.now() - timedelta(days=rng.randint(0, 45), hours=rng.randint(0, 23))
                post = Post(
                    title=title,
                    body=body,
                    author=author,
                    stage=stage,
                    is_published=True,
                    created_at=created_at,
                )
                post.save()
                Post.objects.filter(pk=post.pk).update(created_at=created_at, updated_at=created_at)
                posts.append(post)
        return posts

    def _create_comments(self, posts, users, rng):
        comments = []
        for post in posts:
            total = rng.randint(4, 14)
            parent_comments = []
            for i in range(total):
                user = rng.choice(users)
                is_anon = rng.random() < 0.08
                tone = rng.choice(["agree", "disagree", "ask", "snark"])
                body = self._make_comment_text(tone, rng)
                created_at = post.created_at + timedelta(hours=rng.randint(1, 72))
                comment = Comment.objects.create(
                    post=post,
                    user=None if is_anon else user,
                    is_anon=is_anon,
                    body=body,
                )
                Comment.objects.filter(pk=comment.pk).update(created_at=created_at, updated_at=created_at)
                comments.append(comment)
                parent_comments.append(comment)

            # Add a few replies to simulate debate
            reply_count = rng.randint(1, min(4, len(parent_comments)))
            for _ in range(reply_count):
                parent = rng.choice(parent_comments)
                user = rng.choice(users)
                tone = rng.choice(["disagree", "ask", "snark"])
                body = self._make_comment_text(tone, rng, is_reply=True)
                reply_created_at = parent.created_at + timedelta(hours=rng.randint(1, 24))
                reply = Comment.objects.create(
                    post=post,
                    user=user,
                    is_anon=False,
                    body=body,
                    reply_to=parent,
                )
                Comment.objects.filter(pk=reply.pk).update(created_at=reply_created_at, updated_at=reply_created_at)
        return comments

    def _create_post_reactions(self, posts, users, rng):
        for post in posts:
            like_count = rng.randint(0, min(18, len(users)))
            dislike_count = rng.randint(0, min(6, len(users)))
            like_users = rng.sample(users, like_count) if users else []
            dislike_pool = [u for u in users if u not in like_users]
            dislike_users = rng.sample(dislike_pool, min(dislike_count, len(dislike_pool))) if dislike_pool else []

            Like.objects.bulk_create(
                [Like(user=u, post=post) for u in like_users],
                ignore_conflicts=True,
            )
            DisLike.objects.bulk_create(
                [DisLike(user=u, post=post) for u in dislike_users],
                ignore_conflicts=True,
            )

    def _create_comment_reactions(self, comments, users, rng):
        for comment in comments:
            like_count = rng.randint(0, min(10, len(users)))
            dislike_count = rng.randint(0, min(4, len(users)))
            like_users = rng.sample(users, like_count) if users else []
            dislike_pool = [u for u in users if u not in like_users]
            dislike_users = rng.sample(dislike_pool, min(dislike_count, len(dislike_pool))) if dislike_pool else []

            CommentLike.objects.bulk_create(
                [CommentLike(user=u, comment=comment) for u in like_users],
                ignore_conflicts=True,
            )
            CommentDislike.objects.bulk_create(
                [CommentDislike(user=u, comment=comment) for u in dislike_users],
                ignore_conflicts=True,
            )

    def _make_title(self, stage_name, rng):
        states = [
            "Lagos", "Abuja", "Kano", "Kaduna", "Ibadan", "Enugu", "Port Harcourt",
            "Benin", "Calabar", "Jos", "Owerri", "Uyo", "Abeokuta", "Minna",
        ]
        agencies = ["NBS", "CBN", "NERC", "INEC", "NCDC", "NCC", "FRSC", "FAAN"]
        sectors = ["power", "transport", "education", "health", "agriculture", "telecoms", "banking"]
        issues = ["cost pressures", "service gaps", "new guidelines", "reform plan", "pilot program"]

        news_templates = [
            "{city} residents react as {agency} announces {issue} in {sector}",
            "Report: {sector} spending rises in {city} after {agency} update",
            "{agency} approves {project} linking {city} and {city2}",
            "{city} to pilot {policy} as {sector} faces {issue}",
        ]
        politics_templates = [
            "Lawmakers debate {policy} bill focused on {sector}",
            "Committee hearing set on {policy} and local government funding",
            "Public forum in {city} draws crowds over {policy} reforms",
        ]
        economy_templates = [
            "Market watch: {sector} prices shift in {city} this week",
            "Small businesses in {city} adjust to {policy} changes",
            "Analysts split on {policy} impact for {sector} sector",
        ]
        business_templates = [
            "Local startup launches {product} for {sector} teams",
            "SMEs in {city} share lessons from a tough quarter",
            "Retailers test {policy} incentives in {city}",
        ]
        tech_templates = [
            "Fintech in {city} ships new feature for {sector} payments",
            "Tech community in {city} debates {policy} for innovation",
            "Telco rollout expands coverage across {city}",
        ]
        sports_templates = [
            "{city} club seals dramatic win in weekend fixture",
            "Super Eagles prospects: three players to watch from {city}",
            "Grassroots tournament in {city} draws record turnout",
        ]
        ent_templates = [
            "Afrobeats release week: {city} artists dominate playlists",
            "Nollywood creators in {city} announce new slate",
            "Live show in {city} sparks debate about ticket prices",
        ]
        health_templates = [
            "{city} hospitals begin {policy} quality upgrade program",
            "Health campaign targets {sector} risks in {city}",
            "Clinics in {city} report improved service times",
        ]
        education_templates = [
            "{city} schools test new {policy} for exam prep",
            "Education board in {city} reviews {sector} funding model",
            "Parents in {city} discuss classroom size challenges",
        ]
        energy_templates = [
            "{city} begins {policy} rollout to stabilize power supply",
            "Energy experts in {city} debate {sector} investment plan",
            "Fuel distribution update: {city} stations adjust schedules",
        ]
        culture_templates = [
            "{city} hosts festival celebrating local heritage",
            "Community leaders in {city} discuss cultural preservation",
            "Weekend markets in {city} attract new visitors",
        ]
        transport_templates = [
            "{city} commuters weigh in on {policy} transport pilot",
            "Roadworks in {city} alter peak hour routes",
            "Rail trial between {city} and {city2} gains interest",
        ]

        template_map = {
            "news": news_templates,
            "politics": politics_templates,
            "economy": economy_templates,
            "business": business_templates,
            "tech": tech_templates,
            "sports": sports_templates,
            "ent": ent_templates,
            "health": health_templates,
            "education": education_templates,
            "energy": energy_templates,
            "culture": culture_templates,
            "transport": transport_templates,
        }

        template = rng.choice(template_map.get(stage_name, news_templates))
        return template.format(
            city=rng.choice(states),
            city2=rng.choice(states),
            agency=rng.choice(agencies),
            sector=rng.choice(sectors),
            issue=rng.choice(issues),
            policy=rng.choice(["new policy", "reform proposal", "budget plan", "oversight rules"]),
            project=rng.choice(["rail project", "road upgrade", "health hub", "market expansion"]),
            product=rng.choice(["invoice tool", "logistics app", "analytics suite"]),
        )

    def _make_body(self, stage_name, rng):
        states = [
            "Lagos", "Abuja", "Kano", "Kaduna", "Ibadan", "Enugu", "Port Harcourt",
            "Benin", "Calabar", "Jos", "Owerri", "Uyo", "Abeokuta", "Minna",
        ]
        agencies = ["NBS", "CBN", "NERC", "INEC", "NCDC", "NCC", "FRSC", "FAAN"]
        sectors = ["power", "transport", "education", "health", "agriculture", "telecoms", "banking"]
        themes = {
            "news": ["budget review", "infrastructure push", "public safety update", "service delivery reform"],
            "politics": ["governance reforms", "oversight hearings", "local funding", "electoral logistics"],
            "economy": ["price stability", "market liquidity", "fx policy", "jobs outlook"],
            "business": ["startup funding", "SME support", "retail margins", "supply chain costs"],
            "tech": ["platform policy", "telco expansion", "fintech regulation", "digital skills"],
            "sports": ["league scheduling", "youth development", "stadium upgrades", "club finances"],
            "ent": ["tour logistics", "licensing rules", "talent development", "streaming revenue"],
            "health": ["primary care access", "hospital staffing", "drug supply", "insurance coverage"],
            "education": ["exam reforms", "teacher training", "school funding", "digital classrooms"],
            "energy": ["tariff review", "generation capacity", "grid reliability", "fuel logistics"],
            "culture": ["heritage preservation", "community events", "creative grants", "tourism links"],
            "transport": ["road safety", "rail service", "fare policy", "urban mobility"],
        }

        city = rng.choice(states)
        city2 = rng.choice([s for s in states if s != city] or states)
        agency = rng.choice(agencies)
        sector = rng.choice(sectors)
        topic = rng.choice(themes.get(stage_name, themes["news"]))

        intro = [
            f"In {city}, the conversation this week focused on {topic} and its impact on {sector}.",
            f"Officials from {agency} say the latest steps aim to improve delivery and clarify timelines.",
        ]
        context_pool = [
            f"Local leaders argue that the rollout needs clearer milestones and community feedback loops.",
            f"Small businesses in {city} report early adjustments to staffing and pricing as policies evolve.",
            f"Analysts tracking {sector} indicators say short-term volatility is expected before stability improves.",
            f"Residents in {city2} are watching for whether service levels improve over the next two quarters.",
            f"Stakeholders want more transparency on funding, procurement, and the sequence of implementation.",
        ]
        on_ground_pool = [
            f"On the ground, market traders say demand is steady but margins are tighter than last month.",
            f"Community groups note that communication has improved, but practical support is still uneven.",
            f"Several operators in {city} are testing new workflows while waiting for formal guidance.",
            f"Public reaction remains mixed, with cautious optimism alongside concerns about enforcement.",
            f"Early pilots in {city2} suggest incremental gains, though capacity constraints persist.",
        ]
        outlook_pool = [
            "If the current plan holds, the next phase could focus on measurable service benchmarks.",
            "Most observers agree that sustained monitoring will be as important as the initial announcement.",
            "The biggest open question is whether financing matches the scale of the commitments.",
            "Even supporters say the proof will come from timelines being met and outcomes being published.",
        ]

        paragraph_one = " ".join(intro)
        paragraph_two = " ".join(rng.sample(context_pool, 3))
        paragraph_three = " ".join(rng.sample(on_ground_pool, 3))
        bullets = [
            f"Short-term impact: mixed signals in {sector} costs and availability.",
            f"Operational gap: teams are waiting on clearer guidance from {agency}.",
            "Community response: cautious optimism with calls for accountability.",
            f"Next watchpoint: the next quarterly review and public reporting in {city}.",
        ]
        bullet_block = "Key takeaways:\n- " + "\n- ".join(bullets)
        paragraph_four = " ".join(rng.sample(outlook_pool, 2))
        closer = "Share what you are seeing locally and what you want prioritized next."

        return "\n\n".join([paragraph_one, paragraph_two, paragraph_three, bullet_block, paragraph_four, closer])

    def _make_comment_text(self, tone, rng, is_reply=False):
        agree = [
            "Fair point. The numbers line up with what I see locally.",
            "I agree. This could help if execution is solid.",
            "That makes sense, especially for smaller stages.",
        ]
        disagree = [
            "I disagree. The incentives feel too vague to matter.",
            "Not convinced. We have heard similar promises before.",
            "This reads well on paper but the rollout is the real test.",
        ]
        ask = [
            "Do you have a source or link for this?",
            "Any data on how this affects prices in your area?",
            "How does this compare with last quarter?",
        ]
        snark = [
            "That take feels a bit rushed.",
            "Come on, that is a stretch.",
            "You are missing the point of the proposal.",
        ]
        reply_prefix = "Reply: " if is_reply else ""
        pool = {"agree": agree, "disagree": disagree, "ask": ask, "snark": snark}.get(tone, agree)
        return reply_prefix + rng.choice(pool)
