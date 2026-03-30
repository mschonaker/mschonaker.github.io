# How to Blog From Your Phone for Free

Here's a wild thought: you can write and publish blog posts from your iPhone, on your couch, using your Mac as a remote server - all for zero dollars. Let me show you how.

## The Stack

- **OpenCode** - AI coding assistant that runs as a server
- **OpenCode Zen** - Beautiful UI for mobile
- **Tailscale** - Free VPN to reach your Mac anywhere
- **GitHub Pages** - Free hosting

## Step 1: Tailscale

Set up Tailscale on both your Mac and iPhone (see my previous guide). Once connected, you have a direct tunnel to your Mac from anywhere.

## Step 2: Run OpenCode on Your Mac

On your Mac, start the OpenCode server:

```bash
opencode serve --hostname 0.0.0.0
```

Keep this terminal running (use `caffeinate -i` to prevent sleep).

## Step 3: Access From Your iPhone

Find your Mac's Tailscale IP:

```bash
tailscale ip -4
```

On your iPhone, open your browser and go to:

```
http://100.X.X.X:53640
```

Replace `100.X.X.X` with your Mac's Tailscale IP.

## Step 4: Write

Now you're in. Use **OpenCode Zen** mode for a clean, distraction-free interface. Prompt the model to write your article. Here's a prompt to get started:

```
Write a blog post about [your topic]. Output as markdown that I can drop into my _posts folder.
```

When you're happy, have big pickle write the file directly to your repo:

```
Write this to _posts/my-new-post.md in the current directory
```

Then:

```bash
git add . && git commit -m "new post" && git push
```

GitHub Pages auto-deploys. Your article is live.

## Why This Matters

- No paid hosting
- No expensive laptop needed
- Write from anywhere
- Your Mac does the heavy lifting
- big pickle does the writing

The model is called **big pickle** and it absolutely rules. It handled the entire workflow: starting the server, writing the code, and generating this article. What a chad.

## Conclusion

We live in an era where a phone, a Mac, and some clever free tools can replace an entire dev environment. The future is wild.
