from typing import List, Tuple

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup


class KeyboardBuilder:
    def __init__(
        self,
        selection_prefix: str,
        dir_selection_prefix: str,
        status_callback: str,
        search_movie_callback: str,
        search_tv_callback: str,
        help_keyboard_callback: str,
        download_dir_options: List[Tuple[str, str]],
    ) -> None:
        self._selection_prefix = selection_prefix
        self._dir_selection_prefix = dir_selection_prefix
        self._status_callback = status_callback
        self._search_movie_callback = search_movie_callback
        self._search_tv_callback = search_tv_callback
        self._help_keyboard_callback = help_keyboard_callback
        self._download_dir_options = download_dir_options

    def results_keyboard(self, count: int) -> InlineKeyboardMarkup:
        buttons: List[List[InlineKeyboardButton]] = []
        row: List[InlineKeyboardButton] = []
        for idx in range(1, count + 1):
            row.append(InlineKeyboardButton(str(idx), callback_data=f"{self._selection_prefix}{idx}"))
            if len(row) == 3:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)
        buttons.append([InlineKeyboardButton("📡 Status", callback_data=self._status_callback)])
        return InlineKeyboardMarkup(buttons)

    @staticmethod
    def shortcuts_keyboard() -> ReplyKeyboardMarkup:
        return ReplyKeyboardMarkup(
            [[KeyboardButton("status"), KeyboardButton("help")]],
            resize_keyboard=True,
        )

    def help_keyboard(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("🎬 Search movie", callback_data=self._search_movie_callback),
                    InlineKeyboardButton("📺 Search TV show", callback_data=self._search_tv_callback),
                ],
                [InlineKeyboardButton("📡 Status", callback_data=self._status_callback)],
                [InlineKeyboardButton("Show reply keyboard", callback_data=self._help_keyboard_callback)],
            ]
        )

    def download_dir_keyboard(self) -> InlineKeyboardMarkup:
        buttons: List[List[InlineKeyboardButton]] = [[]]
        for label, path in self._download_dir_options:
            buttons[0].append(InlineKeyboardButton(label, callback_data=f"{self._dir_selection_prefix}{path}"))
        return InlineKeyboardMarkup(buttons)
