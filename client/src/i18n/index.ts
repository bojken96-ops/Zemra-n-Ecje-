import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import LanguageDetector from "i18next-browser-languagedetector";
import it from "./locales/it.json";
import en from "./locales/en.json";
import sq from "./locales/sq.json";

export const SUPPORTED_LANGUAGES = [
  { code: "it", label: "Italiano", flag: "🇮🇹" },
  { code: "en", label: "English", flag: "🇬🇧" },
  { code: "sq", label: "Shqip", flag: "🇦🇱" },
] as const;

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      it: { translation: it },
      en: { translation: en },
      sq: { translation: sq },
    },
    fallbackLng: "it",
    lng: localStorage.getItem("cp_lang") || "it",
    interpolation: { escapeValue: false },
    detection: {
      order: ["localStorage"],
      lookupLocalStorage: "cp_lang",
      caches: ["localStorage"],
    },
  });

export function setLanguage(lang: string) {
  i18n.changeLanguage(lang);
  localStorage.setItem("cp_lang", lang);
  document.documentElement.lang = lang;
}

document.documentElement.lang = i18n.language || "it";

export default i18n;
