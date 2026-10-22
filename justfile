default: site

# Build site/index.html from site/page.html, site/site.toml, site/content/ and results/.
site:
    uv run python tools/build_site.py

# d2 needs one static Inter TTF per weight.
inter := env("INTER_DIR", home_directory() / "Library/Fonts") / "Inter_18pt"

# Re-render docs/diagrams/*.svg; style.d2 is imported by the others.
diagrams:
    for f in docs/diagrams/*.d2; do \
        [ "$f" = docs/diagrams/style.d2 ] || d2 --layout=tala \
            --font-regular={{inter}}-Regular.ttf --font-italic={{inter}}-Italic.ttf \
            --font-bold={{inter}}-Bold.ttf --font-semibold={{inter}}-SemiBold.ttf \
            "$f" "${f%.d2}.svg"; \
    done

all: diagrams site

serve:
    http-server site -p 8083 -c-1
