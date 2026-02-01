from typing import List, Tuple

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


class KeyboardBuilder:
    def __init__(
        self,
        selection_prefix: str,
        dir_selection_prefix: str,
        menu_callback: str,
        search_callback: str,
        help_callback: str,
        status_all_callback: str,
        status_active_callback: str,
        status_refresh_prefix: str,
        cancel_callback: str,
        category_prefix: str,
        page_prefix: str,
        more_like_prefix: str,
        download_dir_options: List[Tuple[str, str]],
    ) -> None:
        self._selection_prefix = selection_prefix
        self._dir_selection_prefix = dir_selection_prefix
        self._menu_callback = menu_callback
        self._search_callback = search_callback
        self._help_callback = help_callback
        self._status_all_callback = status_all_callback
        self._status_active_callback = status_active_callback
        self._status_refresh_prefix = status_refresh_prefix
        self._cancel_callback = cancel_callback
        self._category_prefix = category_prefix
        self._page_prefix = page_prefix
        self._more_like_prefix = more_like_prefix
        self._download_dir_options = download_dir_options

    def main_menu_keyboard(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("Search", callback_data=self._search_callback),
                    InlineKeyboardButton("Status", callback_data=self._status_all_callback),
                    InlineKeyboardButton("Help", callback_data=self._help_callback),
                ],
                [
                    InlineKeyboardButton("Movies", callback_data=f"{self._category_prefix}movies"),
                    InlineKeyboardButton("TV", callback_data=f"{self._category_prefix}tv"),
                    InlineKeyboardButton("Comics", callback_data=f"{self._category_prefix}comics"),
                ],
                [
                    InlineKeyboardButton("Software", callback_data=f"{self._category_prefix}software"),
                    InlineKeyboardButton("mac", callback_data=f"{self._category_prefix}software-mac"),
                    InlineKeyboardButton("win", callback_data=f"{self._category_prefix}software-win"),
                ],
                [
                    InlineKeyboardButton("Zip", callback_data=f"{self._category_prefix}zip"),
                    InlineKeyboardButton("All", callback_data=f"{self._category_prefix}all"),
                ],
            ]
        )

    def back_keyboard(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("Back to menu", callback_data=self._menu_callback)],
            ]
        )

    def search_prompt_keyboard(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("Back", callback_data=self._menu_callback),
                    InlineKeyboardButton("Cancel", callback_data=self._cancel_callback),
                ],
            ]
        )

    def results_keyboard(self, indices: List[int], page: int, total_pages: int) -> InlineKeyboardMarkup:
        buttons: List[List[InlineKeyboardButton]] = []
        for idx in indices:
            buttons.append(
                [
                    InlineKeyboardButton(f"Get #{idx}", callback_data=f"{self._selection_prefix}{idx}"),
                    InlineKeyboardButton(f"More like #{idx}", callback_data=f"{self._more_like_prefix}{idx}"),
                ]
            )

        nav: List[InlineKeyboardButton] = []
        if page > 0:
            nav.append(InlineKeyboardButton("Prev", callback_data=f"{self._page_prefix}{page - 1}"))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton("Next", callback_data=f"{self._page_prefix}{page + 1}"))
        if nav:
            buttons.append(nav)

        buttons.append([InlineKeyboardButton("Back to menu", callback_data=self._menu_callback)])
        return InlineKeyboardMarkup(buttons)

    def status_keyboard(self, active_only: bool) -> InlineKeyboardMarkup:
        all_label = "All *" if not active_only else "All"
        active_label = "Active *" if active_only else "Active"
        refresh_target = "active" if active_only else "all"
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(all_label, callback_data=self._status_all_callback),
                    InlineKeyboardButton(active_label, callback_data=self._status_active_callback),
                    InlineKeyboardButton(
                        "Refresh", callback_data=f"{self._status_refresh_prefix}{refresh_target}"
                    ),
                ],
                [InlineKeyboardButton("Back to menu", callback_data=self._menu_callback)],
            ]
        )

    def download_dir_keyboard(self) -> InlineKeyboardMarkup:
        buttons: List[List[InlineKeyboardButton]] = [[]]
        for label, path in self._download_dir_options:
            buttons[0].append(InlineKeyboardButton(label, callback_data=f"{self._dir_selection_prefix}{path}"))
        return InlineKeyboardMarkup(buttons)
