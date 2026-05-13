#include <stdint.h>

int score_room(int room, int keys, int flags) {
    int score = room * 16 + keys * 9;

    if ((flags & 1) != 0) {
        score += 30;
    } else {
        score -= 4;
    }

    if (keys >= 3) {
        score += keys * room;
    }

    return score ^ (flags << 3);
}
