"""Página de apresentação: contrato de conteúdo e assets locais, sem rede."""
from html.parser import HTMLParser
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class Elements(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.elements = []
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


class PresentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "index.html").read_text(encoding="utf-8")
        cls.elements = Elements(cls.html).elements

    def test_requested_content_order_and_unique_anchors(self):
        sections = [attrs["id"] for tag, attrs in self.elements if tag == "section"]
        self.assertEqual(sections, ["sobre", "pitch", "codigo"])
        ids = [attrs["id"] for _, attrs in self.elements if "id" in attrs]
        self.assertEqual(len(ids), len(set(ids)))
        for tag, attrs in self.elements:
            if tag == "a" and attrs.get("href", "").startswith("#"):
                self.assertIn(attrs["href"][1:], ids)

    def test_local_assets_exist_and_do_not_depend_on_main_app_paths(self):
        for _, attrs in self.elements:
            for field in ("src", "srcset", "href"):
                path = attrs.get(field, "")
                if path and not path.startswith(("https:", "#")):
                    self.assertFalse(path.startswith(("../", "/")))
                    self.assertTrue((ROOT / path).is_file(), path)

    def test_github_destinations_and_safe_external_links(self):
        links = [attrs for tag, attrs in self.elements if tag == "a" and attrs.get("href", "").startswith("https://github.com/")]
        self.assertEqual({a["href"] for a in links}, {
            "https://github.com/sgablopes/spaceinvaders"})
        for link in links:
            self.assertIn("noopener", link["rel"])
            self.assertIn("noreferrer", link["rel"])
        back = next(attrs for tag, attrs in self.elements if tag == "a" and "nav-return" in attrs.get("class", ""))
        self.assertEqual(back["href"], "https://agrion.earth")
        self.assertIn("button-primary", back["class"])
        self.assertIn("Repositório GitHub", self.html)
        self.assertNotIn("Código aberto", self.html)
        self.assertEqual(len(links), 1)
        self.assertIn("para avaliação técnica da proposta", self.html)
        for text in ("DADOS E ANÁLISES", "O projeto é aberto", "CONTRIBUA", "acompanhe o desenvolvimento"):
            self.assertNotIn(text, self.html)

    def test_language_headings_and_truthful_pending_pitch(self):
        self.assertEqual(next(a["lang"] for t, a in self.elements if t == "html"), "pt-BR")
        self.assertEqual(sum(t == "h1" for t, _ in self.elements), 1)
        self.assertIn("disponível aqui em breve", self.html)
        play = next(a for _, a in self.elements if a.get("id") == "pitch-play")
        self.assertIn("hidden", play)
        self.assertTrue(play["aria-label"])
        self.assertNotIn("<iframe", self.html)
        self.assertNotIn("youtube.com/watch?v=", (ROOT / "config.js").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
