// First copy of the lists used by the 19.1.1 data entry wizard. The source is the 19.1.1 code,
// not this project. After the 19.1.1 transfer, these lists are copied again with a version number
// (see docs/plans/FD-08-plan-19.1.1.md).
//   titles:  app/transaction_titles187.py (TRANSACTION_TITLES), app/data_entry_rules187.py (LAND_TITLE)
//   methods: app/barkav/features/dashboard.py (METHOD_FA, the methods without the unknown one)
//   phases:  app/barkav1871/core/phase_catalog.py (32 construction phases)

export const TRANSACTION_TITLES = [
  "هزینه ساخت",
  "ورودی",
  "خروجی",
  "یادداشت",
  "خرید زمین",
  "حقوق مدیر پروژه",
] as const;

export const PAYMENT_METHODS = ["نقدی", "واریز بانکی", "کارت/کارتخوان", "چک", "سایر"] as const;

const PHASE_NAMES = [
  "خرید زمین", "مطالعات اولیه", "طراحی", "نظام مهندسی", "جواز",
  "تجهیز کارگاه", "خاکی و تخریب", "اسکلت", "چاه", "کف سازی",
  "شاسی آسانسور", "وال پست", "میلگرد بستر", "وال مش", "تیغه چینی",
  "تاسیسات", "عایق و بام", "چهارچوب و فریم", "شاسی نما", "آسانسور",
  "درب ضدسرقت", "کاشی و سنگ", "سقف کاذب", "گچکاری", "UPVC",
  "نرده و هندریل", "درب پارکینگ", "نقاشی", "درب اتاق", "انشعابات",
  "پایان کار", "سند و فروش",
];

export const CONSTRUCTION_PHASES = PHASE_NAMES.map(
  (name, index) => `${String(index + 1).padStart(2, "0")} - ${name}`,
);

export const WEATHER_OPTIONS = ["آفتابی", "ابری", "بارانی", "برفی", "بادی", "مه‌آلود"] as const;
