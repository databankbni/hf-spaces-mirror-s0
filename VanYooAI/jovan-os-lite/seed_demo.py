from database import (
    create_tables,
    add_goal,
    set_domain_weight,
)


def seed_demo_data():
    create_tables()

    demo_goals = [
        {
            "domain": "formalno_obrazovanje",
            "title": "Complete university coursework",
            "description": "Make consistent progress on academic or technical coursework.",
            "priority": "high",
        },
        {
            "domain": "neformalno_obrazovanje",
            "title": "Build AI portfolio projects",
            "description": "Create small practical AI systems that can be shown in a portfolio.",
            "priority": "high",
        },
        {
            "domain": "sport",
            "title": "Maintain fitness routine",
            "description": "Keep a consistent training and recovery routine.",
            "priority": "medium",
        },
        {
            "domain": "karijera",
            "title": "Improve career visibility",
            "description": "Create visible outputs such as GitHub updates, demos, posts, or outreach.",
            "priority": "medium",
        },
    ]

    demo_weights = {
        "formalno_obrazovanje": 30,
        "neformalno_obrazovanje": 30,
        "sport": 20,
        "karijera": 20,
    }

    for goal in demo_goals:
        add_goal(
            domain=goal["domain"],
            title=goal["title"],
            description=goal["description"],
            priority=goal["priority"],
        )

    for domain, weight in demo_weights.items():
        set_domain_weight(
            domain=domain,
            weight=weight,
            reason="Demo seed data",
        )


if __name__ == "__main__":
    seed_demo_data()
    print("Demo data seeded successfully.")