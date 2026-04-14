# cluster_diagnostic.py
# Run on the VM: python cluster_diagnostic.py
# Analyzes cluster quality to determine if segmentation is needed
# or if simpler fixes (filtering, concatenation) would suffice.

import sqlite3
import json
import sys

DATABASE_PATH = './data/messages.db'


def get_cluster_messages(db_path):
    """Get all clusters with their messages."""
    conn = sqlite3.connect(db_path)
    try:
        clusters = conn.execute(
            "SELECT id, label, message_count, summary "
            "FROM clusters ORDER BY message_count DESC"
        ).fetchall()

        results = []
        for cid, label, count, summary_json in clusters:
            msgs = conn.execute(
                "SELECT m.content, m.author_name, m.is_bot_author "
                "FROM cluster_messages cm "
                "JOIN messages m ON m.id = cm.message_id "
                "WHERE cm.cluster_id = ? "
                "ORDER BY m.created_at ASC",
                (cid,)
            ).fetchall()

            results.append({
                "id": cid,
                "label": label,
                "message_count": count,
                "summary": summary_json,
                "messages": [
                    {"content": c, "author": a, "is_bot": bool(b)}
                    for c, a, b in msgs
                ],
            })
        return results
    finally:
        conn.close()


def analyze_message(content):
    """Classify a message's semantic density."""
    if not content or not content.strip():
        return "empty"
    words = content.split()
    # Very short messages with no real content
    if len(words) <= 3:
        lower = content.lower().strip().rstrip('!?.)')
        thin = {
            "yes", "no", "ok", "okay", "sure", "agreed", "yep", "nope",
            "right", "exactly", "true", "false", "thanks", "thank you",
            "nice", "cool", "great", "good", "lol", "lmao", "haha",
            "hmm", "hm", "ah", "oh", "wow", "yea", "yeah", "nah",
            "same", "done", "got it", "sounds good", "makes sense",
            "i agree", "i think so", "let's do it", "for sure",
        }
        if lower in thin:
            return "thin"
    if len(words) <= 5:
        return "short"
    if len(words) <= 15:
        return "medium"
    return "substantial"


def analyze_cluster(cluster):
    """Analyze a single cluster's semantic quality."""
    msgs = cluster["messages"]
    if not msgs:
        return None

    categories = {"empty": 0, "thin": 0, "short": 0,
                  "medium": 0, "substantial": 0}
    bot_count = 0
    for msg in msgs:
        cat = analyze_message(msg["content"])
        categories[cat] += 1
        if msg["is_bot"]:
            bot_count += 1

    total = len(msgs)
    thin_pct = (categories["empty"] + categories["thin"]) / total * 100
    short_pct = (categories["empty"] + categories["thin"] +
                 categories["short"]) / total * 100
    bot_pct = bot_count / total * 100

    # Classify cluster quality
    if thin_pct > 50:
        quality = "NOISE"
    elif short_pct > 70:
        quality = "WEAK"
    elif categories["substantial"] / total > 0.4:
        quality = "STRONG"
    else:
        quality = "MODERATE"

    return {
        "quality": quality,
        "total": total,
        "categories": categories,
        "thin_pct": round(thin_pct, 1),
        "short_pct": round(short_pct, 1),
        "bot_pct": round(bot_pct, 1),
    }


def main():
    print("=" * 70)
    print("CLUSTER QUALITY DIAGNOSTIC")
    print("=" * 70)

    clusters = get_cluster_messages(DATABASE_PATH)
    if not clusters:
        print("No clusters found. Run !summary create first.")
        return

    print(f"\nTotal clusters: {len(clusters)}")
    total_msgs = sum(c["message_count"] for c in clusters)
    print(f"Total messages in clusters: {total_msgs}\n")

    quality_counts = {"NOISE": 0, "WEAK": 0, "MODERATE": 0, "STRONG": 0}
    noise_clusters = []
    weak_clusters = []

    for cluster in clusters:
        analysis = analyze_cluster(cluster)
        if not analysis:
            continue

        quality_counts[analysis["quality"]] += 1

        if analysis["quality"] == "NOISE":
            noise_clusters.append((cluster, analysis))
        elif analysis["quality"] == "WEAK":
            weak_clusters.append((cluster, analysis))

    # Summary
    print("-" * 70)
    print("QUALITY DISTRIBUTION")
    print("-" * 70)
    for q, count in quality_counts.items():
        pct = count / len(clusters) * 100 if clusters else 0
        bar = "#" * int(pct / 2)
        print(f"  {q:10s}: {count:3d} ({pct:5.1f}%) {bar}")

    noise_msg_count = sum(a["total"] for _, a in noise_clusters)
    weak_msg_count = sum(a["total"] for _, a in weak_clusters)
    print(f"\n  Messages in NOISE clusters: {noise_msg_count} "
          f"({noise_msg_count/total_msgs*100:.1f}% of total)")
    print(f"  Messages in WEAK clusters:  {weak_msg_count} "
          f"({weak_msg_count/total_msgs*100:.1f}% of total)")

    # Detail on noise clusters
    if noise_clusters:
        print("\n" + "-" * 70)
        print("NOISE CLUSTERS (>50% thin/empty messages)")
        print("-" * 70)
        for cluster, analysis in noise_clusters:
            print(f"\n  [{cluster['label']}] "
                  f"({analysis['total']} msgs, "
                  f"{analysis['thin_pct']}% thin, "
                  f"{analysis['bot_pct']}% bot)")
            # Show first 5 messages as sample
            for msg in cluster["messages"][:5]:
                prefix = "[BOT] " if msg["is_bot"] else ""
                content = msg["content"][:80]
                cat = analyze_message(msg["content"])
                print(f"    {prefix}{msg['author']}: "
                      f"{content} [{cat}]")
            if len(cluster["messages"]) > 5:
                print(f"    ... and {len(cluster['messages']) - 5} more")

    # Detail on weak clusters
    if weak_clusters:
        print("\n" + "-" * 70)
        print("WEAK CLUSTERS (>70% short or thinner)")
        print("-" * 70)
        for cluster, analysis in weak_clusters[:5]:
            print(f"\n  [{cluster['label']}] "
                  f"({analysis['total']} msgs, "
                  f"{analysis['short_pct']}% short-or-less, "
                  f"{analysis['bot_pct']}% bot)")
            for msg in cluster["messages"][:5]:
                prefix = "[BOT] " if msg["is_bot"] else ""
                content = msg["content"][:80]
                cat = analyze_message(msg["content"])
                print(f"    {prefix}{msg['author']}: "
                      f"{content} [{cat}]")
            if len(cluster["messages"]) > 5:
                print(f"    ... and {len(cluster['messages']) - 5} more")

    # Recommendation
    print("\n" + "=" * 70)
    print("RECOMMENDATION")
    print("=" * 70)
    noise_pct = quality_counts["NOISE"] / len(clusters) * 100
    weak_pct = quality_counts["WEAK"] / len(clusters) * 100
    problem_pct = noise_pct + weak_pct

    if problem_pct > 30:
        print(f"  {problem_pct:.0f}% of clusters are NOISE or WEAK.")
        print("  SEGMENTATION is recommended — the clustering unit")
        print("  (individual messages) is too granular. Segment-level")
        print("  embeddings would produce more meaningful clusters.")
    elif problem_pct > 15:
        print(f"  {problem_pct:.0f}% of clusters are NOISE or WEAK.")
        print("  MODERATE issue. Consider concatenating consecutive")
        print("  same-author messages and filtering thin messages")
        print("  from the embedding corpus before full segmentation.")
    else:
        print(f"  {problem_pct:.0f}% of clusters are NOISE or WEAK.")
        print("  Cluster quality is acceptable. Segmentation would")
        print("  be an optimization, not a necessity.")


if __name__ == "__main__":
    main()
