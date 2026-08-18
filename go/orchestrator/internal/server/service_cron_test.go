package server

import (
	"testing"
)

func TestValidateCronSchedule(t *testing.T) {
	tests := []struct {
		name    string
		expr    string
		wantErr bool
	}{
		{
			name:    "valid weekday morning schedule",
			expr:    "0 9 * * 1-5",
			wantErr: false,
		},
		{
			name:    "valid every minute",
			expr:    "* * * * *",
			wantErr: false,
		},
		{
			name:    "valid every hour",
			expr:    "0 * * * *",
			wantErr: false,
		},
		{
			name:    "valid every day at midnight",
			expr:    "0 0 * * *",
			wantErr: false,
		},
		{
			name:    "valid with ranges and lists",
			expr:    "0,30 9-17 * * 1-5",
			wantErr: false,
		},
		{
			name:    "invalid - wrong number of fields",
			expr:    "0 9 *",
			wantErr: true,
		},
		{
			name:    "invalid - bad minute value",
			expr:    "60 * * * *",
			wantErr: true,
		},
		{
			name:    "invalid - bad hour value",
			expr:    "0 25 * * *",
			wantErr: true,
		},
		{
			name:    "invalid - bad day of week",
			expr:    "0 0 * * 8",
			wantErr: true,
		},
		{
			name:    "invalid - garbage input",
			expr:    "not a cron expression",
			wantErr: true,
		},
		{
			name:    "invalid - empty string",
			expr:    "",
			wantErr: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := validateCronSchedule(tt.expr)
			if (err != nil) != tt.wantErr {
				t.Errorf("validateCronSchedule(%q) error = %v, wantErr %v", tt.expr, err, tt.wantErr)
			}
		})
	}
}
